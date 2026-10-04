import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { providerLabel } from "@/lib/format";
import type { ModelConfig } from "@/lib/types";

const AUTO = "auto";

export function ModelPicker({
  value,
  onChange,
  providers,
}: {
  value: ModelConfig;
  onChange: (next: ModelConfig) => void;
  providers: string[];
}) {
  const patch = (partial: Partial<ModelConfig>) => onChange({ ...value, ...partial });
  const specific = value.provider !== AUTO && value.provider !== "";

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="model-provider">Provider</Label>
        <Select
          id="model-provider"
          value={value.provider || AUTO}
          onValueChange={(provider) =>
            patch({
              provider,
              // A named provider needs its own model name; auto picks one for you.
              name: provider === AUTO ? value.name : "",
            })
          }
          options={[
            { value: AUTO, label: "Auto (organization default)", hint: "recommended" },
            ...providers.map((provider) => ({
              value: provider,
              label: providerLabel(provider),
            })),
          ]}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="model-name">Model</Label>
        <Input
          id="model-name"
          value={value.name}
          placeholder={specific ? "e.g. claude-sonnet-5" : "Chosen automatically"}
          disabled={!specific}
          onChange={(event) => patch({ name: event.target.value })}
        />
        <p className="text-xs text-muted-foreground">
          {specific
            ? "The exact model identifier sent to the provider."
            : "Leave on auto to use whatever the organization default points at."}
        </p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="model-temperature">
          Temperature <span className="font-normal text-muted-foreground">{value.temperature}</span>
        </Label>
        <input
          id="model-temperature"
          type="range"
          min={0}
          max={2}
          step={0.1}
          value={value.temperature}
          className="w-full accent-primary"
          onChange={(event) => patch({ temperature: Number(event.target.value) })}
          aria-valuetext={String(value.temperature)}
        />
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>0 · consistent</span>
          <span>2 · varied</span>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="model-max-tokens">Max tokens</Label>
        <Input
          id="model-max-tokens"
          type="number"
          min={256}
          step={256}
          value={value.max_tokens}
          disabled={!specific}
          onChange={(event) => patch({ max_tokens: Number(event.target.value) })}
        />
      </div>
    </div>
  );
}
