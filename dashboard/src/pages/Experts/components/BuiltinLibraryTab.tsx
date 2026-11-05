// Fork-owned: lists the expert templates bundled with the install (GET /api/experts).
// Upstream 1.0.3b3 removed this tab and moved built-in templates to the remote market, but the
// backend endpoint and the create drawer (kind "builtin") are still there. Kept in its own file,
// with its own search and refresh, so merging upstream only touches the tab wiring in ../index.tsx.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Input, Spin } from "antd";
import { RefreshCw, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import cx from "classnames";
import { request } from "../../../api/request";
import PillScroller from "../../../components/PillScroller";
import { OctopEmptyMascot } from "../../../components/EmptyState";
import { apiErrorMessage } from "../../../utils/apiError";
import { ExpertCard } from "./ExpertCard";
import type { ExpertSummary } from "./ExpertCard";
import styles from "../index.module.less";

const SCENE_ALL = "";
const SCENE_ORDER = [
  "ecommerce",
  "finance",
  "content-creation",
  "lifestyle",
  "marketing",
  "mysticism",
  "academic",
  "legal",
  "tech",
  "education",
  "healthcare",
  "hr",
  "media",
  "design",
] as const;

interface BuiltinLibraryTabProps {
  lang: "zh" | "en";
  installedExpertIds: Set<string>;
  onRequestCreate: (expert: ExpertSummary) => void;
}

function matches(
  needle: string,
  expert: ExpertSummary,
  sceneName: string,
): boolean {
  if (!needle) return true;
  return [
    expert.id,
    expert.label?.zh,
    expert.label?.en,
    expert.description?.zh,
    expert.description?.en,
    sceneName,
  ].some((part) => (part || "").toLowerCase().includes(needle));
}

export default function BuiltinLibraryTab({
  lang,
  installedExpertIds,
  onRequestCreate,
}: BuiltinLibraryTabProps) {
  const { t } = useTranslation();
  const [experts, setExperts] = useState<ExpertSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [scene, setScene] = useState(SCENE_ALL);

  const tRef = useRef(t);
  tRef.current = t;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      // The blank "default" seed is what “new expert” already uses; it is not a template card.
      const rows = await request<ExpertSummary[]>("/experts");
      setExperts(rows.filter((row) => row.id !== "default"));
    } catch (err) {
      const tt = tRef.current;
      setError(
        apiErrorMessage(
          err,
          tt("experts.builtinLibraryLoadFailed", "内置专家模板加载失败"),
          tt,
        ),
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const sceneName = useCallback(
    (key: string) => t(`experts.scenes.${key}`, { defaultValue: key }),
    [t],
  );
  const scenes = useMemo(() => {
    const present = new Set(
      experts.map((e) => (e.scene || "").trim()).filter(Boolean),
    );
    return SCENE_ORDER.filter((s) => present.has(s));
  }, [experts]);
  const needle = query.trim().toLowerCase();
  const visible = useMemo(
    () =>
      experts.filter((expert) => {
        const key = (expert.scene || "").trim();
        if (!needle && scene && key !== scene) return false;
        return matches(needle, expert, key ? sceneName(key) : "");
      }),
    [experts, needle, scene, sceneName],
  );

  if (loading && experts.length === 0) {
    return (
      <div className={styles.loadingState}>
        <Spin />
      </div>
    );
  }
  if (error && experts.length === 0) {
    return (
      <div className={styles.emptyState}>
        <OctopEmptyMascot />
        <div className={styles.emptyTitle}>
          {t("experts.builtinLibraryLoadFailed", "内置专家模板加载失败")}
        </div>
        <div className={styles.emptyHint}>{error}</div>
        <div className={styles.emptyActions}>
          <button
            className={styles.toolbarBtn}
            onClick={() => void load()}
            type="button"
          >
            {t("common.refresh")}
          </button>
        </div>
      </div>
    );
  }
  if (experts.length === 0) {
    return (
      <div className={styles.emptyState}>
        <OctopEmptyMascot />
        <div className={styles.emptyTitle}>
          {t("experts.builtinLibraryEmpty", "暂无内置专家模板")}
        </div>
      </div>
    );
  }

  return (
    <>
      <div className={styles.gridToolbar}>
        <span className={styles.gridCount}>
          {t("experts.builtinLibraryCount", {
            defaultValue: "共 {{count}} 个内置专家",
            count: visible.length,
          })}
        </span>
        <div className={styles.gridToolbarRight}>
          <Input
            className={styles.toolbarSearch}
            prefix={<Search size={14} />}
            allowClear
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("experts.builtinLibrarySearch", "搜索内置专家")}
          />
          <button
            className={styles.toolbarIconBtn}
            onClick={() => void load()}
            disabled={loading}
            type="button"
            aria-label={t("common.refresh")}
          >
            <RefreshCw size={14} className={cx(loading && styles.spinning)} />
          </button>
        </div>
      </div>
      {!needle && scenes.length > 0 ? (
        <PillScroller
          options={[
            { value: SCENE_ALL, label: t("experts.sceneAll") },
            ...scenes.map((s) => ({ value: s, label: sceneName(s) })),
          ]}
          active={scene}
          onSelect={setScene}
          prevLabel={t("experts.marketScenePrev")}
          nextLabel={t("experts.marketSceneNext")}
        />
      ) : null}
      {visible.length === 0 ? (
        <div className={styles.searchEmpty}>{t("experts.searchEmpty")}</div>
      ) : (
        <div className={styles.cardGrid}>
          {visible.map((expert) => (
            <ExpertCard
              key={expert.id}
              expert={expert}
              lang={lang}
              isInstalled={installedExpertIds.has(expert.id)}
              onCreate={onRequestCreate}
            />
          ))}
        </div>
      )}
    </>
  );
}
