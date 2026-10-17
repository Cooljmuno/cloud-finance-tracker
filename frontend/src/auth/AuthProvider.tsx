import type { ReactNode } from "react";

import { appConfig } from "../config";
import { CognitoAuthProvider } from "./CognitoAuthProvider";
import { SessionAuthProvider } from "./SessionAuthProvider";

export function AuthProvider({ children }: { children: ReactNode }) {
  if (appConfig.authMode === "cognito") {
    return <CognitoAuthProvider>{children}</CognitoAuthProvider>;
  }
  return <SessionAuthProvider>{children}</SessionAuthProvider>;
}
