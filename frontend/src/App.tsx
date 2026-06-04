import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { QuotePage } from "./pages/QuotePage";
import { BidPage } from "./pages/BidPage";
import { TenderPage } from "./pages/TenderPage";
import { RagPage } from "./pages/RagPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<QuotePage />} />
          <Route path="/bid" element={<BidPage />} />
          <Route path="/tender" element={<TenderPage />} />
          <Route path="/rag" element={<RagPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
