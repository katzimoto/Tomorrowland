import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/styles/base.css";
import "@/styles/utilities.css";
import { Providers } from "@/app/providers";

const root = document.getElementById("root");
if (!root) throw new Error("Root element not found");

createRoot(root).render(
  <StrictMode>
    <Providers />
  </StrictMode>,
);
