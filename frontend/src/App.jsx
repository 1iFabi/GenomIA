// src/App.jsx
import { lazy, Suspense } from "react";
import { Routes, Route, useLocation, Navigate } from "react-router-dom";
import Navbar from "./components/Navbar/Navbar";
import Hero from "./pages/Hero/Hero";
import Loader from "./components/Loader/Loader";
import ProtectedRoute from "./components/ProtectedRoute";
import Login from "./pages/Login/Login";

// Componentes bajo el pliegue (below-the-fold) y rutas secundarias: carga diferida.
const Descubre = lazy(() => import("./pages/Descubre/Descubre"));
const Conoce = lazy(() => import("./pages/Conoce/Conoce"));
const Register = lazy(() => import("./pages/Register/Register"));
const PostloginRouter = lazy(() => import("./pages/Postlogin/PostloginRouter"));
const Profile = lazy(() => import("./pages/Profile/Profile"));
const NoPurchased = lazy(() => import("./pages/NoPurchased/NoPurchased"));
const Pending = lazy(() => import("./pages/Pending/Pending"));
const GenomaPricing = lazy(() => import("./pages/GenomaPricing/GenomaPricing"));
const SobreNosotros = lazy(() => import("./pages/SobreNosotros/SobreNosotros"));
const Contacto = lazy(() => import("./pages/Contacto/Contacto"));
const Preguntas = lazy(() => import("./pages/Preguntas/Preguntas"));
const NotFound = lazy(() => import("./pages/NotFound/NotFound"));

export default function App() {
  const { pathname } = useLocation();
  // Normaliza rutas con barra final (ej: "/login/" -> "/login")
  const normalizedPath = pathname.replace(/\/+$/, "") || "/";
  const isNotFound = normalizedPath === "/404";
  const hideNavbar =
    normalizedPath === "/login" ||
    normalizedPath === "/register" ||
    normalizedPath === "/no-purchased" ||
    normalizedPath === "/pending" ||
    normalizedPath === "/profile" ||
    normalizedPath.startsWith("/dashboard") ||
    isNotFound;

  return (
    <>
      {!hideNavbar && <Navbar />}
      <Suspense fallback={<Loader />}>
        <Routes>
          <Route
            path="/"
            element={
              <>
                <Hero />
                <Suspense fallback={<Loader />}>
                  <Descubre />
                </Suspense>
                <Suspense fallback={<Loader />}>
                  <Conoce />
                </Suspense>
                <Suspense fallback={<Loader />}>
                  <GenomaPricing />
                </Suspense>
                <Suspense fallback={<Loader />}>
                  <Preguntas />
                </Suspense>
                <Suspense fallback={<Loader />}>
                  <SobreNosotros />
                </Suspense>
                <Suspense fallback={<Loader />}>
                  <Contacto />
                </Suspense>
              </>
            }
          />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/no-purchased"
            element={
              <ProtectedRoute requireService={false}>
                <NoPurchased /> 
              </ProtectedRoute>
            }
          />
          <Route
            path="/pending"
            element={
              <ProtectedRoute requireService={false}>
                <Pending />
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/*"
            element={
              <ProtectedRoute>
                <PostloginRouter />
              </ProtectedRoute>
            }
          />
          {/* Página 404 */}
          <Route
            path="/profile"
            element={
              <ProtectedRoute requireService={false}>
                <Profile />
              </ProtectedRoute>
            }
          />
          <Route path="/404" element={<NotFound />} />
          {/* Catch-all: cualquier ruta inexistente redirige a /404 */}
          <Route path="*" element={<Navigate to="/404" replace />} />
        </Routes>
      </Suspense>
    </>
  );
}
