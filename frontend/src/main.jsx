import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import "./styles/index.css";

const savedTheme = localStorage.getItem("theme");
const prefersLight = window.matchMedia?.("(prefers-color-scheme: light)").matches;
document.documentElement.dataset.theme = savedTheme || (prefersLight ? "light" : "dark");

function Main() {
  return (
    <BrowserRouter>
      <App />
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Main />
  </React.StrictMode>
);
