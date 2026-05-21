---
name: tl-tanstack-query-local-state
description: >
  Use this skill when implementing a Tomorrowland React component that fetches server state
  with TanStack Query v5 but also needs to apply local mutations (optimistic messages,
  local appends, edits) without triggering a refetch. Invoke it when the work involves:
  chat sessions or messages, any list that accepts user input before the server round-trip
  completes, components that previously used onSuccess/onError/onSettled on useQuery, or any
  pattern where setQueryData would race with background refetch. The seed-once ref guard
  pattern described here is the established project convention — use it rather than
  inventing a new approach.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: implementation-agents
---

# tl-tanstack-query-local-state

## Context

TanStack Query v5 removed `onSuccess`/`onError`/`onSettled` from `useQuery` options. Components that need to apply local mutations to server-fetched data require a different pattern: seed React state once from the query result, then manage updates locally.

The chat feature (`ChatWindow.tsx`) is the canonical example. Any future component with similar requirements should follow the same approach.

## The seed-once ref guard pattern

```tsx
const { data: messages } = useQuery({
  queryKey: ['chat-messages', session.id],
  queryFn: () => fetchMessages(session.id),
  staleTime: 5 * 60_000,   // prevent background refetch from overwriting local state
});

const [localMessages, setLocalMessages] = useState<Message[]>([]);
const seededForSession = useRef<string | null>(null);

// Seed once when query data arrives for this session
useEffect(() => {
  if (messages && seededForSession.current !== session.id) {
    seededForSession.current = session.id;
    setLocalMessages(messages);
  }
}, [messages, session.id]);

// Reset on session change
useEffect(() => {
  setLocalMessages([]);
  seededForSession.current = null;
}, [session.id]);
```

**Why this approach:**
- `useEffect` replaces the removed `onSuccess` — it runs after render, only when data changes
- The ref guard (`seededForSession.current !== session.id`) prevents re-seeding on background query refetches, which would wipe locally-appended messages
- `staleTime: 5 * 60_000` is a second line of defense — prevents refetch during an active session
- The reset `useEffect` on `session.id` clears both local state and the ref so the next session starts fresh

## Optimistic updates

After a successful mutation, update `localMessages` directly rather than invalidating the query:

```tsx
// User sends a message
const handleSend = async (content: string) => {
  const optimisticMsg: Message = { id: 'temp', role: 'user', content };
  setLocalMessages(prev => [...prev, optimisticMsg]);

  const result = await sendMessage({ sessionId: session.id, content });

  // Replace the optimistic placeholder with the server response (user + assistant)
  setLocalMessages(prev => [
    ...prev.filter(m => m.id !== 'temp'),
    result.userMessage,
    result.assistantMessage,
  ]);
};
```

Do **not** use `queryClient.setQueryData` to append messages — that would cause the seed-once guard to re-seed from the query cache on the next render, overwriting the locally-appended messages.

## When NOT to use this pattern

- Simple read-only data: just use `useQuery` + render directly from `data`.
- Mutations that don't need optimistic UI: use `useMutation` + `invalidateQueries`.
- Only use this pattern when the component needs both server-fetched initial state **and** local writes that must survive background refetch.
