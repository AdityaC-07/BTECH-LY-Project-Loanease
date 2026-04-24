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
    <div className="flex flex-wrap gap-2 mt-3 animate-in fade-in slide-in-from-bottom-2 duration-300">
      {options.map((option) => (
        <Button
          key={option.value}
          variant="outline"
          size="sm"
          onClick={() => onSelect(option.value)}
          className="rounded-full border-yellow-400 bg-background text-yellow-400 hover:bg-yellow-400/10 transition-all text-xs"
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
};
