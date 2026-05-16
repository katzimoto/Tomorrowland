import { createContext, useContext } from "react";

export type ToastKind = "success" | "error" | "info" | "warning";

export interface ToastContextValue {
  show: (kind: ToastKind, message: string) => void;
}

export const ToastContext = createContext<ToastContextValue>({ show: () => {} });

export function useToast() {
  return useContext(ToastContext);
}
