/**
 * End-to-end smoke test for the Clear Price screen.
 *
 * Renders src/App.jsx in a real DOM (jsdom) and drives the form the way a
 * shopper would — typing numbers, pressing "Show Final Price" — against a
 * running FastAPI backend.
 *
 * Run it from the frontend folder, with the backend up:
 *     cd backend && uvicorn main:app --port 8000
 *     cd frontend && npm run test:ui
 *
 * Point it at another backend with TEST_API_URL=https://... npm run test:ui
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BACKEND = (process.env.TEST_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

// The app reads this at build time; setting it here makes the component call the
// backend with an absolute URL, exactly like the deployed build does.
process.env.VITE_API_BASE_URL = BACKEND;
process.env.BACKEND_URL = BACKEND;

// --- is the backend there? -------------------------------------------------- //
try {
  const ping = await fetch(`${BACKEND}/health`, { signal: AbortSignal.timeout(3000) });
  if (!ping.ok) throw new Error(`status ${ping.status}`);
} catch (error) {
  console.error(
    `\nCan't reach the API at ${BACKEND} (${error.message}).\n` +
      "Start it first:  cd backend && uvicorn main:app --port 8000\n"
  );
  process.exit(1);
}

// --- a DOM for the app to render into -------------------------------------- //
const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: "http://localhost:5173/",
  pretendToBeVisual: true,
});

global.window = dom.window;
global.document = dom.window.document;
global.HTMLElement = dom.window.HTMLElement;
global.HTMLInputElement = dom.window.HTMLInputElement;
global.Node = dom.window.Node;
global.Event = dom.window.Event;
global.IS_REACT_ACT_ENVIRONMENT = true;
global.requestAnimationFrame = dom.window.requestAnimationFrame?.bind(dom.window);
global.cancelAnimationFrame = dom.window.cancelAnimationFrame?.bind(dom.window);
dom.window.Element.prototype.scrollIntoView = function () {}; // jsdom has no layout

// --- load and render the real component ------------------------------------ //
const React = (await import("react")).default;
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const { createServer } = await import("vite");

const vite = await createServer({
  root: ROOT,
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "error",
});
const { default: App } = await vite.ssrLoadModule("/src/App.jsx");

const container = document.getElementById("root");
await act(async () => createRoot(container).render(React.createElement(App)));

const inputs = [...document.querySelectorAll("input")];
const form = document.querySelector("form");
const text = () => container.textContent.replace(/\s+/g, " ");

let failures = 0;
const check = (label, condition, extra = "") => {
  console.log(`${condition ? "PASS" : "FAIL"}  ${label}${condition || !extra ? "" : `\n      saw: ${extra}`}`);
  if (!condition) failures += 1;
};

/** Type into a React-controlled input the way the browser does. */
const type = (input, value) => {
  const setter = Object.getOwnPropertyDescriptor(
    dom.window.HTMLInputElement.prototype,
    "value"
  ).set;
  setter.call(input, value);
  input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
};

async function use(price, discount1, discount2 = "") {
  await act(async () => {
    type(inputs[0], price);
    type(inputs[1], discount1);
    type(inputs[2], discount2);
  });
  await act(async () => {
    form.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 300)); // let the request settle
  });
}

// --- the screen itself ------------------------------------------------------ //
check(
  "the screen shows what it needs and nothing else",
  ["Original Price", "Discount 1 (%)", "Discount 2 (%)", "optional", "Show Final Price"].every((s) =>
    text().includes(s)
  )
);
check("no answer before the first calculation", !text().includes("You pay"));
check(
  "all three fields ask for a decimal keypad on phones",
  inputs.length === 3 && inputs.every((i) => i.getAttribute("inputmode") === "decimal")
);
check(
  "every field has a real label",
  inputs.every((i) => !!document.querySelector(`label[for="${i.id}"]`))
);

// --- the maths the whole app exists for ------------------------------------- //
await use("89", "20", "70");
check("$89 with 20% off then 70% off -> you pay $21.36", text().includes("You pay$21.36"), text());
check("$89 with 20% off then 70% off -> you saved $67.64", text().includes("You saved $67.64"));
check("...and the combined discount reads 76%", text().includes("76% off $89.00"));

await use("100", "20", "10");
check("20% off then 10% off on $100 is $72.00 (not the wrong $70.00)", text().includes("$72.00"), text());
check("...and never claims 30% off", text().includes("28% off $100.00") && !text().includes("30% off"));

await use("50", "30");
check("one discount only: $50 with 30% off -> $35.00", text().includes("You pay$35.00"), text());
check("...saved $15.00", text().includes("You saved $15.00"));

await use("89,99", "10");
check("a typed European price '89,99' is read as 89.99", text().includes("$80.99"), text());

await act(async () => type(inputs[0], "10"));
check("changing a number clears the stale answer", !text().includes("You pay"), text());

// --- plain-language guards -------------------------------------------------- //
await use("", "20");
check("empty price -> plain prompt, no answer", text().includes("Type the price on the tag first.") && !text().includes("You pay"), text());

await use("0", "10");
check("price of 0 -> plain prompt", text().includes("The price has to be more than 0."), text());

await use("20", "150");
check("discount above 100 -> plain prompt", text().includes("Discount 1 has to be between 0 and 100."), text());

await use("20", "10", "150");
check("second discount above 100 -> plain prompt", text().includes("Discount 2 has to be between 0 and 100."), text());

console.log(failures === 0 ? "\nAll UI checks passed." : `\n${failures} UI check(s) failed.`);

await vite.close();
dom.window.close();
process.exit(failures === 0 ? 0 : 1);
