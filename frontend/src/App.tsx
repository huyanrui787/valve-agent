import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ChatPage } from "./pages/ChatPage";
import { BidPageV3 } from "./pages/BidPageV3";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RagPage } from "./pages/RagPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<ChatPage />} />
          <Route path="/bid" element={<BidPageV3 />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/rag" element={<RagPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
