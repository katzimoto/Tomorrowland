export interface Translations {
  nav: {
    search: string;
    qa: string;
    subscriptions: string;
    notifications: string;
    history: string;
    expertise: string;
    admin: string;
    settings: string;
    collapse: string;
    expand: string;
    primary: string;
    unread: (n: number) => string;
  };
  app: {
    loadingApp: string;
    loadFailed: string;
    loadFailedBody: string;
  };
  auth: {
    heading: string;
    sessionExpired: string;
    email: string;
    emailInvalid: string;
    password: string;
    passwordRequired: string;
    badCredentials: string;
    genericError: string;
    signIn: string;
    signInLabel: string;
  };
  search: {
    title: string;
    button: string;
    modeGroup: string;
    modeHybrid: string;
    modeKeyword: string;
    modeSemantic: string;
    resultCount: (n: number) => string;
    activeFilters: string;
    removeFilter: (label: string) => string;
    resultsLabel: string;
    unavailableTitle: string;
    unavailableBody: string;
    retry: string;
    noResultsTitle: string;
    noResultsBody: string;
    emptyTitle: string;
    emptyBody: string;
    failedToast: string;
  };
  filters: {
    panel: string;
    fileType: string;
    translation: string;
    clear: string;
    clearAll: string;
    typePdf: string;
    typeOffice: string;
    typeEmail: string;
    typeArchive: string;
    typeText: string;
    typeImage: string;
    transFast: string;
    transHigh: string;
  };
  document: {
    notFoundTitle: string;
    notFoundBody: string;
    tryAgain: string;
    backToSearch: string;
    untitled: string;
    requestTranslation: string;
    download: string;
  };
  insight: {
    tabSummary: string;
    tabQa: string;
    tabRelated: string;
    tabAnnotations: string;
    tabComments: string;
    tabSubscriptions: string;
    summaryLoading: string;
    summaryFailedTitle: string;
    summaryFailedBody: string;
    summaryEmptyTitle: string;
    summaryEmptyBody: string;
    generatedBy: (model: string, date: string) => string;
    entities: string;
    tags: string;
    relatedLoading: string;
    relatedFailedTitle: string;
    relatedFailedBody: string;
    relatedEmptyTitle: string;
    relatedEmptyBody: string;
    annotationsLoading: string;
    annotationsFailedTitle: string;
    annotationsFailedBody: string;
    annotationsEmpty: string;
    annotationPrivate: string;
    annotationShared: string;
    annotationDeleteLabel: string;
    annotationAddPlaceholder: string;
    annotationNewLabel: string;
    annotationPrivateLabel: string;
    annotationAddBtn: string;
    annotationAddError: string;
    annotationDeleteError: string;
    commentsLoading: string;
    commentsEmpty: string;
    commentsLoadMore: string;
    commentsLoadingMore: string;
    commentEditLabel: string;
    commentDeleteLabel: string;
    commentSaveBtn: string;
    commentCancelBtn: string;
    commentAddPlaceholder: string;
    commentNewLabel: string;
    commentPostBtn: string;
    commentPostError: string;
    commentUpdateError: string;
    commentDeleteError: string;
    subscriptionsTitle: string;
    subscriptionsBody: string;
  };
  qa: {
    title: string;
    ask: string;
    failedTitle: string;
    failedBody: string;
    emptyTitle: string;
    emptyBody: string;
    toastError: string;
  };
  notifications: {
    title: string;
    loading: string;
    failedTitle: string;
    failedBody: string;
    emptyTitle: string;
    emptyBody: string;
    unread: string;
    earlier: string;
  };
  subscriptions: {
    title: string;
    newBtn: string;
    active: string;
    notifBadge: string;
    loading: string;
    failedTitle: string;
    failedBody: string;
    emptyTitle: string;
    emptyBody: string;
    createBtn: string;
    editTitle: string;
    newTitle: string;
    saveError: string;
    deleteError: string;
    statusActive: string;
    statusPaused: string;
    pause: string;
    resume: string;
    deleteLabel: (name: string) => string;
    newCount: (n: number) => string;
    nameLabel: string;
    nameRequired: string;
    queryLabel: string;
    queryRequired: string;
    thresholdLabel: (pct: number) => string;
    enabledLabel: string;
    saveBtn: string;
    cancelBtn: string;
  };
  history: {
    title: string;
    privacy: string;
    loading: string;
    failedTitle: string;
    failedBody: string;
    emptyTitle: string;
    emptyBody: string;
    loadMore: string;
    loadingMore: string;
    untitled: string;
    mimeImage: string;
    mimePdf: string;
    mimeWord: string;
    mimeExcel: string;
    mimePpt: string;
    mimeHtml: string;
    mimeText: string;
    mimeEmail: string;
    mimeFile: string;
  };
  expertise: {
    title: string;
    subtitle: string;
    topicLabel: string;
    placeholder: string;
    findBtn: string;
    loading: string;
    failedTitle: string;
    failedBody: string;
  };
  comments: {
    ariaLabel: string;
    unavailableTitle: string;
    unavailableBody: string;
    failedTitle: string;
    failedBody: string;
    emptyTitle: string;
    emptyBody: string;
  };
  annotations: {
    ariaLabel: string;
    unavailableTitle: string;
    unavailableBody: string;
    failedTitle: string;
    failedBody: string;
    emptyTitle: string;
    emptyBody: string;
  };
  admin: {
    title: string;
    addSource: string;
    noSourcesTitle: string;
    noSourcesBody: string;
    colName: string;
    colType: string;
    colLang: string;
    colEnabled: string;
    colActions: string;
    syncBtn: string;
    syncResult: (indexed: number, skipped: number, failed: number) => string;
    dialogTitle: string;
    nameLabel: string;
    namePlaceholder: string;
    typeLabel: string;
    langLabel: string;
    settingsLabel: (label: string) => string;
    createError: string;
    saveBtn: string;
    cancelBtn: string;
  };
  cmd: {
    ariaLabel: string;
    placeholder: string;
    hint: string;
    empty: string;
  };
  lang: {
    label: string;
    en: string;
    he: string;
  };
}

export const en: Translations = {
  nav: {
    search: "Search",
    qa: "Q&A",
    subscriptions: "Subscriptions",
    notifications: "Notifications",
    history: "History",
    expertise: "Expertise",
    admin: "Admin",
    settings: "Settings",
    collapse: "Collapse navigation",
    expand: "Expand navigation",
    primary: "Primary navigation",
    unread: (n) => `${n} unread`,
  },
  app: {
    loadingApp: "Loading application",
    loadFailed: "Failed to load",
    loadFailedBody: "Could not connect to the server. Reload the page to try again.",
  },
  auth: {
    heading: "Sign in to Tomorrowland",
    sessionExpired: "Your session expired. Sign in again.",
    email: "Email",
    emailInvalid: "Enter a valid email",
    password: "Password",
    passwordRequired: "Password is required",
    badCredentials: "Email or password is incorrect.",
    genericError: "Something went wrong. Try again.",
    signIn: "Sign in",
    signInLabel: "Sign in",
  },
  search: {
    title: "Search",
    button: "Search",
    modeGroup: "Search mode",
    modeHybrid: "Hybrid",
    modeKeyword: "Keyword",
    modeSemantic: "Semantic",
    resultCount: (n) => `${n.toLocaleString()} result${n !== 1 ? "s" : ""}`,
    activeFilters: "Active filters",
    removeFilter: (label) => `Remove filter: ${label}`,
    resultsLabel: "Search results",
    unavailableTitle: "Search unavailable",
    unavailableBody: "The search backend is not reachable. Check the server and try again.",
    retry: "Retry",
    noResultsTitle: "No results found",
    noResultsBody: "No accessible documents match your query. Try different terms or remove filters.",
    emptyTitle: "Start searching",
    emptyBody: "Type a query above and press Enter or Search.",
    failedToast: "Search failed. Check that the backend is reachable.",
  },
  filters: {
    panel: "Search filters",
    fileType: "File type",
    translation: "Translation",
    clear: "Clear",
    clearAll: "Clear all filters",
    typePdf: "PDF",
    typeOffice: "Office",
    typeEmail: "Email",
    typeArchive: "Archive",
    typeText: "Text",
    typeImage: "Image",
    transFast: "Fast translation",
    transHigh: "High quality",
  },
  document: {
    notFoundTitle: "Document not found",
    notFoundBody: "This document may have been deleted or you may not have access.",
    tryAgain: "Try again",
    backToSearch: "Back to search",
    untitled: "Untitled document",
    requestTranslation: "Request translation",
    download: "Download",
  },
  insight: {
    tabSummary: "Summary",
    tabQa: "Q&A",
    tabRelated: "Related",
    tabAnnotations: "Annotations",
    tabComments: "Comments",
    tabSubscriptions: "Subscriptions",
    summaryLoading: "Loading…",
    summaryFailedTitle: "Failed to load summary",
    summaryFailedBody: "Could not reach the server.",
    summaryEmptyTitle: "No summary",
    summaryEmptyBody: "AI summary not yet available for this document.",
    generatedBy: (model, date) => `Generated by ${model} · ${date}`,
    entities: "Entities",
    tags: "Tags",
    relatedLoading: "Loading…",
    relatedFailedTitle: "Failed to load related documents",
    relatedFailedBody: "Could not reach the server.",
    relatedEmptyTitle: "No related documents",
    relatedEmptyBody: "No related documents found.",
    annotationsLoading: "Loading…",
    annotationsFailedTitle: "Failed to load annotations",
    annotationsFailedBody: "Could not reach the server.",
    annotationsEmpty: "No annotations yet.",
    annotationPrivate: "Private note",
    annotationShared: "Shared with readers",
    annotationDeleteLabel: "Delete annotation",
    annotationAddPlaceholder: "Add an annotation…",
    annotationNewLabel: "New annotation",
    annotationPrivateLabel: "Private",
    annotationAddBtn: "Add",
    annotationAddError: "Failed to add annotation.",
    annotationDeleteError: "Failed to delete annotation.",
    commentsLoading: "Loading…",
    commentsEmpty: "No comments yet.",
    commentsLoadMore: "Load more comments",
    commentsLoadingMore: "Loading more comments…",
    commentEditLabel: "Edit comment",
    commentDeleteLabel: "Delete comment",
    commentSaveBtn: "Save",
    commentCancelBtn: "Cancel",
    commentAddPlaceholder: "Add a comment…",
    commentNewLabel: "New comment",
    commentPostBtn: "Post",
    commentPostError: "Failed to post comment.",
    commentUpdateError: "Failed to update comment.",
    commentDeleteError: "Failed to delete comment.",
    subscriptionsTitle: "Subscriptions",
    subscriptionsBody: "Subscribe to alerts for this document. Coming in Phase 08e.",
  },
  qa: {
    title: "Q&A",
    ask: "Ask",
    failedTitle: "Request failed",
    failedBody: "The Q&A service is not reachable. Check the server and try again.",
    emptyTitle: "Ask anything",
    emptyBody: "Type a question and press Ask. Answers are grounded in your accessible documents.",
    toastError: "Q&A request failed. Check that the backend is reachable.",
  },
  notifications: {
    title: "Notifications",
    loading: "Loading…",
    failedTitle: "Failed to load notifications",
    failedBody: "Could not reach the server.",
    emptyTitle: "No notifications",
    emptyBody: "You'll be notified here when documents match your subscriptions.",
    unread: "Unread",
    earlier: "Earlier",
  },
  subscriptions: {
    title: "Subscriptions",
    newBtn: "New subscription",
    active: "Active subscriptions",
    notifBadge: "Notifications",
    loading: "Loading…",
    failedTitle: "Failed to load subscriptions",
    failedBody: "Could not reach the server.",
    emptyTitle: "No subscriptions",
    emptyBody: "Create one from scratch or subscribe to a saved search.",
    createBtn: "Create subscription",
    editTitle: "Edit subscription",
    newTitle: "New subscription",
    saveError: "Failed to save subscription.",
    deleteError: "Failed to delete subscription.",
    statusActive: "Active",
    statusPaused: "Paused",
    pause: "Pause",
    resume: "Resume",
    deleteLabel: (name) => `Delete ${name}`,
    newCount: (n) => `${n} new`,
    nameLabel: "Name",
    nameRequired: "Name is required",
    queryLabel: "Query",
    queryRequired: "Query is required",
    thresholdLabel: (pct) => `Threshold: ${pct}%`,
    enabledLabel: "Enabled",
    saveBtn: "Save subscription",
    cancelBtn: "Cancel",
  },
  history: {
    title: "History",
    privacy: "Activity visible only to you and admins.",
    loading: "Loading…",
    failedTitle: "Failed to load history",
    failedBody: "Could not reach the server.",
    emptyTitle: "No history",
    emptyBody: "Documents you view will appear here.",
    loadMore: "Load more history",
    loadingMore: "Loading more history…",
    untitled: "Untitled document",
    mimeImage: "Image",
    mimePdf: "PDF",
    mimeWord: "Word",
    mimeExcel: "Excel",
    mimePpt: "PowerPoint",
    mimeHtml: "HTML",
    mimeText: "Text",
    mimeEmail: "Email",
    mimeFile: "File",
  },
  expertise: {
    title: "Expertise map",
    subtitle: "Find colleagues through document evidence. Results are not rankings or performance scores.",
    topicLabel: "Topic",
    placeholder: "e.g. incident response",
    findBtn: "Find evidence",
    loading: "Loading evidence…",
    failedTitle: "Could not load expertise evidence",
    failedBody: "Try again later.",
  },
  comments: {
    ariaLabel: "Comments",
    unavailableTitle: "Comments unavailable",
    unavailableBody: "You do not have access to this document's collaboration notes.",
    failedTitle: "Could not load comments",
    failedBody: "Try again later.",
    emptyTitle: "No comments yet",
    emptyBody: "Start the conversation for readers with access.",
  },
  annotations: {
    ariaLabel: "Annotations",
    unavailableTitle: "Annotations unavailable",
    unavailableBody: "You do not have access to this document's annotations.",
    failedTitle: "Could not load annotations",
    failedBody: "Try again later.",
    emptyTitle: "No annotations yet",
    emptyBody: "Add private notes or share evidence with readers.",
  },
  admin: {
    title: "Sources",
    addSource: "Add Source",
    noSourcesTitle: "No sources yet",
    noSourcesBody: "Add a source to start ingesting documents.",
    colName: "Name",
    colType: "Type",
    colLang: "Language",
    colEnabled: "Enabled",
    colActions: "Actions",
    syncBtn: "Sync",
    syncResult: (indexed, skipped, failed) =>
      `Indexed: ${indexed}  Skipped: ${skipped}  Failed: ${failed}`,
    dialogTitle: "Add Source",
    nameLabel: "Name",
    namePlaceholder: "e.g. Legal Documents",
    typeLabel: "Type",
    langLabel: "Source language",
    settingsLabel: (label) => `${label} settings`,
    createError: "Failed to create source.",
    saveBtn: "Save Source",
    cancelBtn: "Cancel",
  },
  cmd: {
    ariaLabel: "Command menu",
    placeholder: "Type a destination…",
    hint: "Visible navigation remains available in the rail. Use this shortcut for faster routing.",
    empty: "No matching destinations.",
  },
  lang: {
    label: "Language",
    en: "English",
    he: "עברית",
  },
};
