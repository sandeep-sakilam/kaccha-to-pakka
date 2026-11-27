import { useTranslation } from "react-i18next";
import { BigButton } from "@/components/ui";

/** What a ledger line records: money received, money paid, or goods given on credit (udhaar). */
export type EntryChoice = "in" | "out" | "credit";
export type PaidBy = "cash" | "upi" | null;

export function choiceOf(e: { direction: "in" | "out"; kind?: string }): EntryChoice {
  return e.kind === "credit_given" ? "credit" : e.direction;
}

/** The API fields for a choice. Goods on credit moved no money, so they have no payment method. */
export function entryFields(choice: EntryChoice, paidBy: PaidBy) {
  return choice === "credit"
    ? { direction: "out" as const, kind: "credit_given" as const, paid_by: null }
    : { direction: choice, kind: "money" as const, paid_by: paidBy };
}

export function EntryKindPicker({
  choice,
  onChoice,
  paidBy,
  onPaidBy,
}: {
  choice: EntryChoice;
  onChoice: (c: EntryChoice) => void;
  paidBy: PaidBy;
  onPaidBy: (p: PaidBy) => void;
}) {
  const { t } = useTranslation();
  const labels: Record<EntryChoice, string> = {
    in: t("readback.received"),
    out: t("readback.paid"),
    credit: t("readback.credit"),
  };
  return (
    <>
      <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label={t("readback.what_happened")}>
        {(["in", "out", "credit"] as const).map((c) => (
          <BigButton key={c} variant={choice === c ? "primary" : "secondary"} aria-pressed={choice === c} onClick={() => onChoice(c)}>
            {labels[c]}
          </BigButton>
        ))}
      </div>
      {choice !== "credit" && (
        <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label={t("readback.how_paid")}>
          {([null, "cash", "upi"] as const).map((p) => (
            <BigButton key={p ?? "unsaid"} variant={paidBy === p ? "primary" : "secondary"} aria-pressed={paidBy === p} onClick={() => onPaidBy(p)}>
              {t(p === null ? "readback.not_said" : p === "cash" ? "readback.cash" : "readback.upi")}
            </BigButton>
          ))}
        </div>
      )}
    </>
  );
}
