// src/main.jsx
import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import "./index.css";
import "./styles/scroll-fix.css";
import { GenominProvider } from "./context/GenominContext";
import { AuthProvider } from "./contexts/AuthContext";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <AuthProvider>
        <GenominProvider>
          <App />
        </GenominProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
