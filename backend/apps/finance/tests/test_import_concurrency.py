import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection, connections
from rest_framework.test import APIClient

from apps.finance.models import ImportBatch, Transaction
from apps.users.models import User


@pytest.mark.django_db(transaction=True)
def test_simultaneous_identical_imports_write_one_batch_and_one_set_of_transactions(user, account):
    if connection.vendor != "postgresql":
        pytest.skip("Concurrent import locking must be verified against PostgreSQL.")

    content = (
        b"transaction_date,description,amount,status,notes\n"
        b"2026-10-17,Synthetic market,-12.50,posted,Sample purchase\n"
        b"2026-10-18,Synthetic transport,-3.00,posted,Sample fare\n"
    )
    client = APIClient()
    client.force_authenticate(user=user)
    preview = client.post(
        "/api/v1/imports/preview/",
        {
            "account": str(account.id),
            "file": SimpleUploadedFile("statement.csv", content, content_type="text/csv"),
        },
        format="multipart",
    )
    assert preview.status_code == 200, preview.data
    token = preview.data["preview_token"]
    owner_id = user.id
    account_id = str(account.id)
    barrier = threading.Barrier(2)

    def commit_on_independent_connection():
        close_old_connections()
        try:
            owner = User.objects.get(pk=owner_id)
            thread_client = APIClient()
            thread_client.force_authenticate(user=owner)
            barrier.wait(timeout=10)
            response = thread_client.post(
                "/api/v1/imports/commit/",
                {
                    "account": account_id,
                    "file": SimpleUploadedFile("statement.csv", content, content_type="text/csv"),
                    "preview_token": token,
                },
                format="multipart",
            )
            return response.status_code, response.data
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(commit_on_independent_connection) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]

    assert sorted(code for code, _ in results) == [200, 201], results
    assert sorted(data["duplicate"] for _, data in results) == [False, True]
    assert len({data["batch"]["id"] for _, data in results}) == 1
    assert ImportBatch.objects.filter(account=account).count() == 1
    batch = ImportBatch.objects.get(account=account)
    assert batch.row_count == 2
    assert Transaction.objects.filter(account=account, import_batch=batch).count() == 2
