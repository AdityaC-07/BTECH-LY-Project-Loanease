import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Sun, Moon } from "lucide-react";
import Index from "./pages/Index";
import LandingPage from "./pages/LandingPage";
import BlockchainExplorer from "./pages/BlockchainExplorer";
import WhatsAppPage from "./pages/WhatsAppPage";
import BlockchainVerificationPortal from "./pages/BlockchainVerificationPortal";
import NotFound from "./pages/NotFound";
import { DemoChecklist } from "./components/DemoChecklist";
import { useTheme } from "./hooks/useTheme";

const queryClient = new QueryClient();

const ThemeToggle = () => {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      onClick={toggleTheme}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={theme === "dark" ? "Light mode" : "Dark mode"}
      className="fixed bottom-5 right-5 z-50 rounded-full w-10 h-10 flex items-center justify-center bg-card border border-border shadow-lg hover:shadow-xl transition-all hover:scale-110"
    >
      {theme === "dark"
        ? <Sun  className="w-4 h-4 text-accent" aria-hidden="true" />
        : <Moon className="w-4 h-4 text-accent" aria-hidden="true" />}
    </button>
  );
};

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/whatsapp" element={<WhatsAppPage />} />
          <Route path="/blockchain/explorer" element={<BlockchainExplorer />} />
          <Route path="/blockchain/verify" element={<BlockchainVerificationPortal />} />
          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
      {/* Demo checklist — visible only when ?demo=true in URL */}
      <DemoChecklist />
      {/* Dark/light mode toggle — bottom-right floating button */}
      <ThemeToggle />
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;