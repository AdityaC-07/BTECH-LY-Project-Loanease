import { cn } from "@/lib/utils";
import { Bot, User, Check, CheckCheck } from "lucide-react";

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
        "flex gap-3 animate-slide-up",
        isBot ? "justify-start" : "justify-end"
      )}
    >
      {isBot && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary flex items-center justify-center">
          <Bot className="w-4 h-4 text-primary-foreground" />
        </div>
      )}
      <div className="flex flex-col gap-1">
        <div
          className={cn(
            "max-w-[80%] rounded-2xl px-4 py-3 text-sm",
            isBot
              ? "bg-card border border-border text-card-foreground rounded-tl-md"
              : "bg-primary text-primary-foreground rounded-tr-md"
          )}
        >
          {isTyping ? (
            <div className="flex gap-1 py-1">
              <span className="w-2 h-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-2 h-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-2 h-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
          ) : (
            <p className="whitespace-pre-wrap">{message}</p>
          )}
        </div>
        {!isBot && (
          <div className="flex items-center justify-end gap-1 px-1">
            <span className="text-[10px] text-muted-foreground/60">
              {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
            <div className="flex">
              {status === "sent" && <Check className="w-3 h-3 text-muted-foreground/40" />}
              {status === "delivered" && <CheckCheck className="w-3 h-3 text-muted-foreground/40" />}
              {status === "responded" && <CheckCheck className="w-3 h-3 text-yellow-400" />}
            </div>
          </div>
        )}
      </div>
      {!isBot && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-accent flex items-center justify-center">
          <User className="w-4 h-4 text-accent-foreground" />
        </div>
      )}
    </div>
  );
};
