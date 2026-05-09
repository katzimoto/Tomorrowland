import { createRouter, createRoute, createRootRoute, redirect } from "@tanstack/react-router";
import { authStorage } from "@/api/auth";
import { LoginPage } from "@/features/auth/LoginPage";
import { AppLayout } from "./AppLayout";
import { PlaceholderPage } from "./PlaceholderPage";

function requireAuth() {
  if (!authStorage.hasToken()) {
    throw redirect({ to: "/login" });
  }
}

const rootRoute = createRootRoute();

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
});

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "app",
  beforeLoad: requireAuth,
  component: AppLayout,
});

const indexRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/",
  beforeLoad: () => { throw redirect({ to: "/search" }); },
});

const searchRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/search",
  component: () => <PlaceholderPage title="Search" />,
});

const qaRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/qa",
  component: () => <PlaceholderPage title="Q&A" />,
});

const subscriptionsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/subscriptions",
  component: () => <PlaceholderPage title="Subscriptions" />,
});

const notificationsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/notifications",
  component: () => <PlaceholderPage title="Notifications" />,
});

const historyRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/history",
  component: () => <PlaceholderPage title="History" />,
});

const settingsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/settings/profile",
  component: () => <PlaceholderPage title="Settings" />,
});

const adminRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin",
  component: () => <PlaceholderPage title="Admin" />,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  appRoute.addChildren([
    indexRoute,
    searchRoute,
    qaRoute,
    subscriptionsRoute,
    notificationsRoute,
    historyRoute,
    settingsRoute,
    adminRoute,
  ]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
