# Frontend conventions (frozen interfaces)

Every page and component slice is written against this. Do not rename an export or change a
prop signature without updating the file that owns it — and never edit a file you do not own.

## Ground rules

1. React 18 + TypeScript strict + Vite. No `any` unless a third-party type forces it.
2. Tailwind only. **Never hard-code a colour.** Use the tokens: `bg-background`,
   `text-foreground`, `bg-card`, `text-muted-foreground`, `border-border`, `text-primary`,
   `bg-primary`, `text-destructive`, `text-success`, `text-warning`, `bg-muted`, `bg-accent`,
   `ring-ring`. Accent + light/dark come from CSS variables.
3. Mobile-first. Everything must work at 360px. No horizontal scrolling except inside an
   explicitly `overflow-x-auto` element.
4. Accessibility: semantic elements, `<label htmlFor>`, `aria-*` where needed, visible focus
   (handled globally by `:focus-visible`), keyboard-operable dialogs/menus (Radix gives this).
5. Icons: `lucide-react` only. Toasts: `sonner` (`toast.success`, `toast.error`). Dates:
   helpers in `@/lib/format`.
6. Vocabulary: the product is **Buttlr**; each AI employee is a **Buttlr**. Never write "agent",
   "bot", "workflow" or "automation" in user-visible strings.
7. Copy tone: calm, concrete, no marketing. Empty states invite an action; errors say what
   happened and what to do.
8. Import alias `@/` → `src/`.

## Available library layer (already written — do not modify)

`@/lib/types` — every domain type, snake_case, mirrors the backend exactly.
`@/lib/api` — `api.*`, `ApiError`, `tokenStore`, `activeOrgStore`, `streamExecution`.
`@/lib/queries` — `keys`, read hooks (`useButtlrs`, `useDashboard`, `useApprovals`, …), mutation
hooks (`useDraftButtlr`, `useDecideApproval`, …) and `useExecutionStream`.
`@/lib/auth` — `useAuth()` → `{status, user, organizations, activeOrganizationId,
activeOrganization, login, logout, setActiveOrganization, refresh, applyUser}`.
`@/lib/theme` — `useTheme()` → `{theme, accent, density, resolvedTheme, setTheme, setAccent,
setDensity}`.
`@/lib/format` — `formatDateTime, formatDate, formatRelative, formatDuration, formatTokens,
formatCost, humanize, toolLabel, providerLabel, initials, toneFor`.
`@/lib/utils` — `cn(...)`.
`@/lib/constants` — `DEPARTMENTS`, `GITHUB_LABELS`? no — only `DEPARTMENTS`, `ACCENTS`,
`SCHEDULE_PRESETS`. (Ceate it only if you own it: `FE1` owns `src/lib/constants.ts`.)

## `src/components/ui/*` (owned by FE1)

Styled primitives with `forwardRef`. Named exports exactly as below.

```
button.tsx      Button({variant?: "default"|"secondary"|"outline"|"ghost"|"destructive"|"success", size?: "sm"|"md"|"lg"|"icon", loading?: boolean, asChild?: boolean} & ButtonHTMLAttributes), buttonVariants
input.tsx       Input (InputHTMLAttributes)
textarea.tsx    Textarea (TextareaHTMLAttributes)
label.tsx       Label (Radix Label)
select.tsx      Select({value, onValueChange, options: {value,label,hint?}[], placeholder?, disabled?, className?, id?, "aria-label"?}) — native <select> styled; also NativeSelect = Select
card.tsx        Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter
badge.tsx       Badge({tone?: "default"|"muted"|"success"|"warning"|"destructive"|"primary"|"outline"})
avatar.tsx      Avatar({name?, src?, emoji?, size?: "xs"|"sm"|"md"|"lg"})
dialog.tsx      Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogClose
dropdown-menu.tsx DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuCheckboxItem
tabs.tsx        Tabs, TabsList, TabsTrigger, TabsContent
tooltip.tsx     Tooltip, TooltipTrigger, TooltipContent, TooltipProvider
switch.tsx      Switch({checked, onCheckedChange, disabled?, id?})
separator.tsx   Separator({orientation?})
skeleton.tsx    Skeleton({className})
progress.tsx    Progress({value?: number, className?})
table.tsx       Table, TableHeader, TableBody, TableRow, TableHead, TableCell
alert.tsx       Alert({tone?: "info"|"success"|"warning"|"destructive", title?, children?, icon?})
```

## `src/components/common/*` (owned by FE1)

```
FullPageSpinner({label?})                       // already imported by App.tsx
Spinner({className?})
EmptyState({icon?: LucideIcon, title, description?, action?: ReactNode, className?})
ErrorState({error: unknown, onRetry?: () => void, title?})
PageHeader({title, description?, actions?: ReactNode, back?: {to: string, label: string}})
StatCard({label, value: ReactNode, hint?, icon?: LucideIcon, tone?: "default"|"success"|"warning"|"destructive", loading?})
StatusPill({status: ButtlrStatus|ExecutionStatus|ApprovalStatus|IntegrationStatus, size?: "sm"|"md"})
RiskBadge({risk: RiskLevel})
ConfirmDialog({open, onOpenChange, title, description?, confirmLabel?, cancelLabel?, onConfirm, loading?, destructive?})
CopyButton({value, label?})
SectionCard({title, description?, actions?, children, className?})   // Card + header used by every settings/detail section
Field({label, hint?, error?, htmlFor?, required?, children})         // form field wrapper
```

`StatusPill` maps: active/completed/connected/approved → success; running/queued → primary;
waiting_approval/pending/paused/blocked → warning; failed/error/rejected → destructive;
draft/disabled/expired/cancelled → muted. Always renders an icon **and** text (never colour
alone). Import `toneFor` from `@/lib/format` for the mapping.

## `src/components/layout/*` (owned by FE2)

```
AppShell()        // route element; renders Sidebar (desktop) + Topbar + <Outlet/> + MobileNav
Sidebar()         // desktop nav: Overview, Buttlrs, Teams, Approvals, Integrations, Activity, Analytics; footer: Settings, user
Topbar()          // mobile header: menu button, org switcher, notifications, user menu; desktop: breadcrumb/title area + notifications + user
MobileNav()       // fixed bottom bar: Overview, Buttlrs, Approvals, Activity, More(sheet with the rest)
OrgSwitcher()     // dropdown over useAuth().organizations + "Create organization" → /onboarding
NotificationBell() // dropdown of recent notifications, unread dot, "Mark all read"
UserMenu()        // profile, settings, theme quick toggle, sign out
```

Navigation items (exact labels/order): Overview, Buttlrs, Teams, Approvals, Integrations,
Activity, Analytics, then Organization (Settings). Approval count badge on Approvals from
`useApprovalStats`.

## `src/components/buttlr/*` (owned by FE2)

```
ButtlrCard({buttlr, href?, pendingApprovals?, className?})
ButtlrAvatar({buttlr, size?})
ScheduleBadge({schedule})
ExecutionTimeline({execution, live?})      // real steps: icon per StepType, status, duration, tool, approval link
ActivityTimeline({items, loading?})        // AuditLog[]
ApprovalCard({approval, canDecide, onDecide(granted, note?), loading?})
IntegrationCard({integration, entry, onRefresh, onDisconnect, onUpdateScopes, busy?})
ToolPicker({tools, value, onChange})       // checkbox list grouped by integration, shows risk/permission
PermissionMatrix({buttlr, teams, members}) // grants by subject with permission level
ScopeEditor({scope, onChange, integrations})// repositories (from integration resources) + free-form keys
ModelPicker({value, onChange, providers})   // ModelConfig editor: provider select, model text, temperature
```

## Pages (named exports, one file each)

| File | Export | Owner |
| --- | --- | --- |
| `src/pages/LoginPage.tsx` | `LoginPage` | FE3 |
| `src/pages/OnboardingPage.tsx` | `OnboardingPage` | FE3 |
| `src/pages/OverviewPage.tsx` | `OverviewPage` | FE3 |
| `src/pages/ButtlrsPage.tsx` | `ButtlrsPage` | FE3 |
| `src/pages/TeamsPage.tsx` | `TeamsPage` | FE3 |
| `src/pages/ButtlrNewPage.tsx` | `ButtlrNewPage` | FE4 |
| `src/pages/ButtlrDetailPage.tsx` | `ButtlrDetailPage` | FE4 |
| `src/pages/ApprovalsPage.tsx` | `ApprovalsPage` | FE5 |
| `src/pages/IntegrationsPage.tsx` | `IntegrationsPage` | FE5 |
| `src/pages/ActivityPage.tsx` | `ActivityPage` | FE5 |
| `src/pages/AnalyticsPage.tsx` | `AnalyticsPage` | FE5 |
| `src/pages/SettingsPage.tsx` | `SettingsPage` | FE5 |
| `src/pages/NotFoundPage.tsx` | `NotFoundPage` | FE5 |

## Data rules

* Never call `fetch` — use `@/lib/api` or the hooks in `@/lib/queries`.
* Reads: hooks. Writes: mutation hooks + `toast.success/error`; use `mutation.isPending`.
* Loading → `Skeleton` rows (not spinners) inside content areas; error → `ErrorState`.
* Empty → `EmptyState` with a real next action.
* The active organization is `useAuth().activeOrganizationId`; never read it from the URL.
* `useEffect` is a last resort; derive from data instead.
