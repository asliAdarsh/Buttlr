import { Suspense, lazy } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { FullPageSpinner } from "@/components/common/FullPageSpinner";
import { useAuth } from "@/lib/auth";

/**
 * Pages are code-split: the shell and the first screen load immediately, everything else
 * arrives on navigation. Keeps the initial bundle small on mobile connections.
 */
const LoginPage = lazy(() => import("@/pages/LoginPage").then((m) => ({ default: m.LoginPage })));
const OnboardingPage = lazy(() =>
  import("@/pages/OnboardingPage").then((m) => ({ default: m.OnboardingPage })),
);
const OverviewPage = lazy(() =>
  import("@/pages/OverviewPage").then((m) => ({ default: m.OverviewPage })),
);
const ButtlrsPage = lazy(() =>
  import("@/pages/ButtlrsPage").then((m) => ({ default: m.ButtlrsPage })),
);
const ButtlrNewPage = lazy(() =>
  import("@/pages/ButtlrNewPage").then((m) => ({ default: m.ButtlrNewPage })),
);
const ButtlrDetailPage = lazy(() =>
  import("@/pages/ButtlrDetailPage").then((m) => ({ default: m.ButtlrDetailPage })),
);
const ApprovalsPage = lazy(() =>
  import("@/pages/ApprovalsPage").then((m) => ({ default: m.ApprovalsPage })),
);
const IntegrationsPage = lazy(() =>
  import("@/pages/IntegrationsPage").then((m) => ({ default: m.IntegrationsPage })),
);
const ActivityPage = lazy(() =>
  import("@/pages/ActivityPage").then((m) => ({ default: m.ActivityPage })),
);
const AnalyticsPage = lazy(() =>
  import("@/pages/AnalyticsPage").then((m) => ({ default: m.AnalyticsPage })),
);
const TeamsPage = lazy(() => import("@/pages/TeamsPage").then((m) => ({ default: m.TeamsPage })));
const SettingsPage = lazy(() =>
  import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);
const NotFoundPage = lazy(() =>
  import("@/pages/NotFoundPage").then((m) => ({ default: m.NotFoundPage })),
);

export function App() {
  const { status, organizations } = useAuth();
  const location = useLocation();

  if (status === "loading") return <FullPageSpinner label="Loading Buttlr…" />;

  if (status === "anonymous") {
    return (
      <Suspense fallback={<FullPageSpinner />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="*"
            element={<Navigate to="/login" replace state={{ from: location.pathname }} />}
          />
        </Routes>
      </Suspense>
    );
  }

  if (organizations.length === 0) {
    return (
      <Suspense fallback={<FullPageSpinner />}>
        <Routes>
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="*" element={<Navigate to="/onboarding" replace />} />
        </Routes>
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<FullPageSpinner />}>
      <Routes>
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route element={<AppShell />}>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/buttlrs" element={<ButtlrsPage />} />
          <Route path="/buttlrs/new" element={<ButtlrNewPage />} />
          <Route path="/buttlrs/:buttlrId" element={<ButtlrDetailPage />} />
          <Route path="/approvals" element={<ApprovalsPage />} />
          <Route path="/integrations" element={<IntegrationsPage />} />
          <Route path="/activity" element={<ActivityPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/teams" element={<TeamsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
