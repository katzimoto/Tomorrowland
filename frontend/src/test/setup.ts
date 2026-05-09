import "@testing-library/jest-dom";
import { vi } from "vitest";

// jsdom does not implement HTMLDialogElement native methods; the open attribute
// must be toggled manually so role="dialog" is discoverable by testing-library.
HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
  this.setAttribute("open", "");
});
HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
  this.removeAttribute("open");
});
