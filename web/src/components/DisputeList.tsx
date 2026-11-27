import { useTranslation } from "react-i18next";
import { istDate } from "@/lib/format";
import { Card } from "./ui";

export type DisputeRow = { id: string; target_type: string; reason: string | null; status: string; resolution: string | null; created_at: string };

export function DisputeList({ rows }: { rows: DisputeRow[] }) {
  const { t, i18n } = useTranslation();
  if (rows.length === 0) return <p>{t("disputes.none")}</p>;
  return (
    <ul className="flex flex-col gap-2" data-testid="dispute-list">
      {rows.map((d) => (
        <li key={d.id}>
          <Card>
            <p className="font-semibold">{d.reason}</p>
            <p className="text-sm">
              {istDate(d.created_at, i18n.language)} · {t(`disputes.status_${d.status}`)}
            </p>
            {d.resolution && <p>{t(`disputes.res_${d.resolution}`)}</p>}
          </Card>
        </li>
      ))}
    </ul>
  );
}
