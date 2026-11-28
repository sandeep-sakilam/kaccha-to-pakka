import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { choiceOf, entryFields, EntryKindPicker, type EntryChoice, type PaidBy } from "@/components/EntryKind";
import { Keypad } from "@/components/Keypad";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";
import { api } from "@/lib/api";
import { rupeesInWords, speak } from "@/lib/voice";

type Item = {
  entry: { id: string; amount_paise: number; direction: "in" | "out"; kind?: string; paid_by?: PaidBy; party_text: string | null };
  prompt: string;
  reason: "low_confidence" | "page_total";
};

export default function ReadBack() {
  const { t, i18n } = useTranslation();
  const { businessId = "" } = useParams();
  const nav = useNavigate();
  const [items, setItems] = useState<Item[] | null>(null);
  const [fixing, setFixing] = useState(false);
  const [amount, setAmount] = useState("");
  const [choice, setChoice] = useState<EntryChoice>("in");
  const [paidBy, setPaidBy] = useState<PaidBy>(null);

  const load = useCallback(async () => {
    const data = await api<Item[]>(`/businesses/${businessId}/readback?language=${i18n.language}`);
    setItems(data);
    if (data[0]) void speak([data[0].prompt], i18n.language);
    else void speak([t("readback.all_done")], i18n.language);
  }, [businessId, i18n.language, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const current = items?.[0];

  async function answer(body: Record<string, unknown>) {
    if (!current) return;
    await api(`/ledger/${current.entry.id}/confirm`, { method: "POST", json: body });
    setFixing(false);
    setAmount("");
    await load();
  }

  return (
    <Screen title={t("readback.title")} spoken={current ? [current.prompt] : [t("readback.all_done")]}>
      {items === null && <p role="status">{t("common.loading")}</p>}
      {items && !current && (
        <>
          <p className="text-lg" role="status">
            {t("readback.all_done")}
          </p>
          <BigButton onClick={() => nav("/home")}>{t("capture.done")}</BigButton>
        </>
      )}
      {current && (
        <>
          <p className="text-sm text-gray-600">{t("readback.left", { count: items!.length })}</p>
          <Card>
            <p className="text-sm text-gray-600">{t(`readback.reason_${current.reason}`)}</p>
            <p className="mt-2 text-2xl font-semibold" data-testid="readback-prompt">
              {current.prompt}
            </p>
          </Card>
          {!fixing ? (
            <div className="grid grid-cols-2 gap-3">
              <BigButton icon="👍" onClick={() => void answer({ correct: true })}>
                {t("common.yes")}
              </BigButton>
              <BigButton
                variant="secondary"
                icon="👎"
                onClick={() => {
                  setFixing(true);
                  setChoice(choiceOf(current.entry));
                  setPaidBy(current.entry.paid_by ?? null);
                  void speak([t("readback.correct_amount")], i18n.language);
                }}
              >
                {t("common.no")}
              </BigButton>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <p className="font-semibold">{t("readback.correct_amount")}</p>
              <p className="rounded-2xl bg-white p-4 text-center text-3xl font-bold tabular-nums text-ink shadow-sm ring-1 ring-black/10" aria-live="polite">
                ₹ {amount || "0"}
                {amount && <span className="block text-base">{rupeesInWords(Number(amount) * 100, i18n.language)}</span>}
              </p>
              <Keypad value={amount} onChange={setAmount} max={9} />
              <EntryKindPicker choice={choice} onChoice={setChoice} paidBy={paidBy} onPaidBy={setPaidBy} />
              <BigButton
                onClick={() =>
                  void answer({ correct: false, ...(amount ? { amount_paise: Number(amount) * 100 } : {}), ...entryFields(choice, paidBy) })
                }
              >
                {t("readback.save")}
              </BigButton>
              <BigButton variant="danger" onClick={() => void answer({ correct: false })}>
                {t("readback.not_mine")}
              </BigButton>
            </div>
          )}
        </>
      )}
    </Screen>
  );
}
