import { Button } from "./ui/button";

interface QuickReply {
  label: string;
  value: string;
}

interface QuickRepliesProps {
  options: QuickReply[];
  onSelect: (value: string) => void;
}

export const QuickReplies = ({ options, onSelect }: QuickRepliesProps) => {
  return (
    <div className="flex flex-nowrap overflow-x-auto overflow-y-hidden pb-2 scrollbar-hide gap-2 mt-2 animate-in fade-in slide-in-from-bottom-2 duration-300">
      {options.map((option) => (
        <Button
          key={option.value}
          variant="outline"
          size="sm"
          onClick={() => onSelect(option.value)}
          className="rounded-full shrink-0 border-yellow-400 bg-background text-yellow-400 hover:bg-yellow-400/10 transition-all text-xs"
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
};
