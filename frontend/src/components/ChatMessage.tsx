import { cn } from "@/lib/utils";
import { Bot, Check, CheckCheck } from "lucide-react";

interface ChatMessageProps {
  message: string;
  isBot: boolean;
  isTyping?: boolean;
  status?: "sent" | "delivered" | "responded";
}

export const ChatMessage = ({ message, isBot, isTyping, status = "responded" }: ChatMessageProps) => {
  return (
    <div
      className={cn(
        "flex gap-2 animate-slide-up w-full",
        isBot ? "justify-start" : "justify-end"
      )}
    >
      {isBot && (
        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-yellow-400 flex items-center justify-center mt-auto mb-1 border-2 border-background shadow-sm z-10">
          <Bot className="w-4 h-4 text-black" />
        </div>
      )}
      
      <div className={cn(
        "flex flex-col max-w-[85%] relative group",
        isBot ? "items-start" : "items-end"
      )}>
        <div
          className={cn(
            "relative px-4 py-2.5 text-sm shadow-sm",
            isBot
              ? "bg-[#2a2b2e] text-white rounded-2xl rounded-bl-none border border-border/50"
              : "bg-yellow-400 text-black rounded-2xl rounded-br-none"
          )}
        >
          {isTyping ? (
            <div className="flex gap-1 py-1.5 px-1">
              <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce opacity-70" style={{ animationDelay: "0ms" }} />
              <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce opacity-70" style={{ animationDelay: "150ms" }} />
              <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce opacity-70" style={{ animationDelay: "300ms" }} />
            </div>
          ) : (
            <p className="whitespace-pre-wrap leading-relaxed">{message}</p>
          )}

          {!isTyping && (
            <div className={cn(
              "flex items-center gap-1 mt-1 justify-end",
              isBot ? "opacity-60" : "opacity-80"
            )}>
              <span className="text-[10px] leading-none">
                {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
              
              {!isBot && (
                <div className="flex -mr-1">
                  {status === "sent" && <Check className="w-3.5 h-3.5 text-black/60" />}
                  {status === "delivered" && <CheckCheck className="w-3.5 h-3.5 text-black/60" />}
                  {status === "responded" && <CheckCheck className="w-3.5 h-3.5 text-blue-600" />}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
