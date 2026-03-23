import { useState } from "react";
import { Hero } from "@/components/Hero";
import { ChatInterface } from "@/components/ChatInterface";

const Index = () => {
  const [showChat, setShowChat] = useState(false);

  return (
    <>
      <Hero onStartChat={() => setShowChat(true)} />
      {showChat && <ChatInterface onClose={() => setShowChat(false)} />}
    </>
  );
};

export default Index;
