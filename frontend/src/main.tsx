import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, isStaff, useAuth } from "./lib/auth";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import Login from "./pages/Login";
import Exams from "./pages/Exams";
import ExamDetail from "./pages/ExamDetail";
import ReviewQueue from "./pages/ReviewQueue";
import ReviewAnswer from "./pages/ReviewAnswer";
import Users from "./pages/Users";
import MyPapers from "./pages/MyPapers";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: false } },
});

function App() {
  const { session, loading, me, meError, signOut } = useAuth();
  if (loading) return <Spinner />;
  if (!session) return <Login />;
  if (meError) {
    return (
      <div className="mx-auto mt-24 max-w-md space-y-3 text-center">
        <p>Your account isn't linked to a college yet. Ask your college admin to add you.</p>
        <button className="text-indigo-700 underline" onClick={signOut}>Sign out</button>
      </div>
    );
  }
  if (!me) return <Spinner />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={isStaff(me) ? <Exams /> : <MyPapers />} />
        <Route path="my-papers" element={<MyPapers />} />
        <Route path="exams/:examId" element={<ExamDetail />} />
        <Route path="exams/:examId/review" element={<ReviewQueue />} />
        <Route path="exams/:examId/review/:answerId" element={<ReviewAnswer />} />
        {me.role === "admin" && <Route path="users" element={<Users />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
