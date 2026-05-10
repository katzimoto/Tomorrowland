import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { test, expect, vi } from "vitest";
import { screen, render, waitFor } from "@/test/render";
import { markRead, type Notification } from "@/api/notifications";
import { NotificationItem } from "./NotificationItem";

const navigate = vi.fn();
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigate }));
vi.mock("@/api/notifications", () => ({ markRead: vi.fn(() => Promise.resolve({ id: "n1", read: true })) }));

const notification: Notification = {
  id: "n1",
  subscription_id: "s1",
  subscription_name: "Risk",
  subscription_query: "risk",
  doc_id: "d1",
  doc_title: "Doc",
  similarity: 0.8,
  read: false,
  created_at: "2026-05-10T00:00:00Z",
};

test("renders unread notification action", () => {
  render(<NotificationItem notification={notification} />);
  expect(screen.getByText("New")).toBeInTheDocument();
  expect(screen.getByRole("button")).toHaveTextContent("Doc");
});

test("rolls back optimistic mark-read state when the API fails", async () => {
  const user = userEvent.setup();
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData<Notification[]>(["notifications"], [notification]);
  queryClient.setQueryData<Notification[]>(["notifications-unread"], [notification]);
  let rejectRead: (error: Error) => void = () => undefined;
  vi.mocked(markRead).mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectRead = reject; }));

  function Probe() {
    const { data = [] } = useQuery<Notification[]>({
      queryKey: ["notifications-unread"],
      queryFn: () => Promise.resolve([]),
      staleTime: Infinity,
    });
    return <span data-testid="unread-count">{data.length}</span>;
  }

  render(
    <QueryClientProvider client={queryClient}>
      <NotificationItem notification={notification} />
      <Probe />
    </QueryClientProvider>,
  );

  await user.click(screen.getByRole("button"));
  await waitFor(() => expect(screen.getByTestId("unread-count")).toHaveTextContent("0"));

  rejectRead(new Error("offline"));

  await waitFor(() => expect(screen.getByTestId("unread-count")).toHaveTextContent("1"));
});
