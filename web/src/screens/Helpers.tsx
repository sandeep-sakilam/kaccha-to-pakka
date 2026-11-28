import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { Keypad } from "@/components/Keypad";
import { Screen } from "@/components/Screen";
import { BigButton, Card } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

const PERMS = ["capture", "voice_entry", "readback", "import", "statement", "invite", "passport"];
type Link = { id: string; sahayak_name: string | null; phone_last4: string; permissions: string[]; revoked_at: string | null };

export default function Helpers() {
  const { t } = useTranslation();
  const { businessId = "" } = useParams();
  const [links, setLinks] = useState<Link[]>([]);
  const [phone, setPhone] = useState("");
  const [perms, setPerms] = useState<string[]>(["capture", "voice_entry", "readback"]);
  const [womenOnly, setWomenOnly] = useState(false);
  // The business setting: only women helpers may be added (on by default for women-owned).
  const [onlyWomen, setOnlyWomen] = useState(false);
  const [directory, setDirectory] = useState<{ name: string; phone_last4: string }[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => setLinks(await api<Link[]>(`/businesses/${businessId}/sahayaks`)), [businessId]);
  useEffect(() => {
    void load();
    void api<{ women_helpers_only?: boolean }>(`/businesses/${businessId}`)
      .then((b) => {
        setOnlyWomen(!!b.women_helpers_only);
        if (b.women_helpers_only) setWomenOnly(true);
      })
      .catch(() => undefined);
  }, [load, businessId]);

  async function setRule(on: boolean) {
    const b = await api<{ women_helpers_only: boolean }>(`/businesses/${businessId}`, { method: "PATCH", json: { women_helpers_only: on } });
    setOnlyWomen(b.women_helpers_only);
    if (b.women_helpers_only) setWomenOnly(true);
  }
  useEffect(() => {
    void api<{ name: string; phone_last4: string }[]>(`/sahayak/directory?women_only=${womenOnly}`).then(setDirectory);
  }, [womenOnly]);

  async function add() {
    setError(null);
    try {
      await api(`/businesses/${businessId}/sahayaks`, { method: "POST", json: { phone, permissions: perms } });
      setPhone("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.error"));
    }
  }

  return (
    <Screen title={t("sahayak.helpers_title")} spoken={[t("sahayak.helpers_intro")]}>
      <p>{t("sahayak.helpers_intro")}</p>
      {links
        .filter((l) => !l.revoked_at)
        .map((l) => (
          <Card key={l.id} className="flex items-center justify-between gap-2">
            <span>
              {l.sahayak_name} (…{l.phone_last4}) · {l.permissions.map((p) => t(`sahayak.perm_${p}`)).join(", ")}
            </span>
            <button type="button" className="min-h-12 rounded-xl bg-red-700 px-3 text-white" onClick={() => void api(`/businesses/${businessId}/sahayaks/${l.id}/revoke`, { method: "POST" }).then(load)}>
              {t("sahayak.remove")}
            </button>
          </Card>
        ))}
      <label className="flex min-h-12 items-center gap-3 font-semibold">
        <input type="checkbox" className="h-6 w-6" checked={onlyWomen} onChange={(e) => void setRule(e.target.checked)} />
        {t("sahayak.women_helpers_only")}
      </label>
      <label className="flex min-h-12 items-center gap-3">
        <input type="checkbox" className="h-6 w-6" checked={womenOnly} disabled={onlyWomen} onChange={(e) => setWomenOnly(e.target.checked)} />
        {t("sahayak.women_only")}
      </label>
      <ul className="text-sm">{directory.map((d) => <li key={d.phone_last4 + d.name}>{d.name} (…{d.phone_last4})</li>)}</ul>
      <p className="rounded-2xl bg-white p-4 text-center text-3xl font-bold tabular-nums text-ink shadow-sm ring-1 ring-black/10">+91 {phone || "__________"}</p>
      <Keypad value={phone} onChange={setPhone} max={10} />
      <div className="grid grid-cols-2 gap-2">
        {PERMS.map((p) => (
          <BigButton key={p} variant={perms.includes(p) ? "primary" : "secondary"} aria-pressed={perms.includes(p)} onClick={() => setPerms((cur) => (cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]))}>
            {t(`sahayak.perm_${p}`)}
          </BigButton>
        ))}
      </div>
      <BigButton disabled={phone.length !== 10 || perms.length === 0} onClick={add}>
        {t("sahayak.add")}
      </BigButton>
      {error && <p role="alert">{error}</p>}
    </Screen>
  );
}
