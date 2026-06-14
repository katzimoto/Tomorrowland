export interface Translations {
  nav: {
    search: string;
    qa: string;
    chat: string;
    subscriptions: string;
    notifications: string;
    history: string;
    expertise: string;
    admin: string;
    settings: string;
    sourceHealth: string;
    collapse: string;
    expand: string;
    primary: string;
    unread: (n: number) => string;
    signOut: string;
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
    signUp: string;
    signUpLink: string;
    signUpTitle: string;
    displayName: string;
    confirmPassword: string;
    passwordMismatch: string;
    duplicateEmail: string;
    signUpSuccess: string;
    signInLink: string;
  };
  search: {
    title: string;
    button: string;
    modeGroup: string;
    modeHybrid: string;
    modeKeyword: string;
    modeSemantic: string;
    resultCount: (n: number) => string;
    resultApproximate: (n: number) => string;
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
    keyboardHelp: string;
    updating: string;
    retrievalDegraded: string;
    quickPreviewTitle: string;
    openSelected: string;
    closePreview: string;
    loadMore: string;
    loadingMore: string;
    previewLabel: string;
    preview: (title: string) => string;
    whyThisResult: string;
    savePassage: string;
    today: string;
    daysAgo: (n: number) => string;
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
    includeOlderVersions: string;
    sortBy: string;
    sortRelevance: string;
    sortUpdated: string;
    sortCreated: string;
    advanced: string;
    extension: string;
    tags: string;
    source: string;
  };
  document: {
    notFoundTitle: string;
    notFoundBody: string;
    tryAgain: string;
    backToSearch: string;
    untitled: string;
    requestTranslation: string;
    download: string;
    downloadText: string;
    downloadTranslation: string;
    downloadError: string;
  };
  preview: {
    loading: string;
    preparing: string;
    bodyUnavailable: string;
    emailBodyLabel: string;
    emailRegion: string;
    bodyView: string;
    viewFormatted: string;
    viewText: string;
    showQuoted: string;
    subject: string;
    from: string;
    to: string;
    cc: string;
    date: string;
    blockedImages: (n: number) => string;
    attachments: (n: number) => string;
    attachmentOf: string;
    sheetRegion: string;
    sheetTabs: string;
    sheetTruncated: string;
    rerender: string;
  };
  insight: {
    tabSummary: string;
    tabQa: string;
    tabChat: string;
    tabRelated: string;
    tabAnnotations: string;
    tabComments: string;
    tabSubscriptions: string;
    tabVersions: string;
    tabDetails: string;
    versionLatest: string;
    versionOlder: string;
    versionBannerTitle: string;
    versionBannerLink: string;
    versionsLoading: string;
    versionsFailedTitle: string;
    versionsFailedBody: string;
    versionsEmpty: string;
    versionLabel: (n: number) => string;
    summaryLoading: string;
    summaryFailedTitle: string;
    summaryFailedBody: string;
    summaryEmptyTitle: string;
    summaryEmptyBody: string;
    generatedBy: (model: string, date: string) => string;
    entities: string;
    entitiesFailed: string;
    tags: string;
    tagsFailed: string;
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
    whyRelated: string;
    relationScore: (score: string) => string;
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
  chat: {
    pageTitle: string;
    newChat: string;
    startChat: string;
    emptyTitle: string;
    emptyBody: string;
    noChatsYet: string;
    loadChatsError: string;
    loadSessionError: string;
    deleteSession: string;
    deleteError: string;
    sendError: string;
    inputPlaceholder: string;
    send: string;
    groundingNote: string;
    sourcesHeading: string;
    chattingWith: string;
    scopeAll: string;
    scopeSingleDocument: string;
    scopeSelectedDocuments: string;
    scopeSelectedDocumentsCount: (n: number) => string;
    scopeSource: string;
    scopeFolder: string;
    scopeSearchResults: string;
    untitledDocument: string;
    scopeSwitchLabel: string;
    askAboutSelected: string;
    retry: string;
    starterHeading: string;
    openDocument: string;
    saveToEvidencePack: string;
    saveEvidence: string;
    evidenceClose: string;
    evidenceLoading: string;
    evidenceNotFound: string;
    evidenceForbidden: string;
    evidenceNoPreview: string;
    evidenceOpenFullPage: string;
    evidenceTabEvidence: string;
    evidenceTabSource: string;
    evidenceTabRetrieval: string;
    evidenceTabActions: string;
    evidenceChunkIndex: string;
    evidenceOriginalLanguage: string;
    evidenceTranslatedFrom: string;
    evidenceSourceId: string;
    evidencePageSection: string;
    evidenceRetrievalTrace: string;
    evidenceRetrievalStages: string;
    evidenceRetrievalCandidates: string;
    evidenceRetrievalNoTrace: string;
    evidenceRetrievalReranked: string;
    evidenceRetrievalDegraded: string;
    evidenceCopyCitation: string;
    evidenceCopied: string;
    evidenceReportBadCitation: string;
    evidenceBackends: string;
    evidenceFusedRank: string;
    evidenceRerankerDelta: string;
    evidenceFinalContextRank: string;
    evidenceRetrievalDegradedBackends: string;
    evidenceScopeFiltered: string;
    evidenceDedupCount: string;
    evidenceScoreThresholdFiltered: string;
    evidenceRerankerDropped: string;
    evidenceSourceHealth: string;
    evidenceSourceHealthHealthy: string;
    evidenceSourceHealthDegraded: string;
    evidenceSourceHealthFailed: string;
    evidenceSourceHealthUnknown: string;
    evidenceSourceHealthNoData: string;
    feedbackTypeCorrect: string;
    feedbackTypeWrongPassage: string;
    feedbackTypeWrongLocation: string;
    feedbackTypeMissingSource: string;
    feedbackTypeUnsupported: string;
    feedbackTypePermission: string;
    feedbackTypeOther: string;
    feedbackComment: string;
    feedbackSubmit: string;
    feedbackSubmitting: string;
    feedbackSuccess: string;
    feedbackError: string;
    feedbackDuplicate: string;
    phaseSearching: string;
    phaseReadingSources: string;
    phaseGenerating: string;
    translatedFrom: (lang: string) => string;
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
    colLastSync: string;
    colActions: string;
    syncBtn: string;
    testConnectionBtn: string;
    testConnectionOk: string;
    testConnectionError: string;
    neverSynced: string;
    syncStatusSuccess: string;
    syncStatusPartialFailure: string;
    syncStatusFailed: string;
    lastSynced: (value: string) => string;
    syncResult: (enqueued: number, skipped: number, failed: number) => string;
    syncStarted: (name: string) => string;
    syncCompleted: (
      enqueued: number,
      skipped: number,
      failed: number,
    ) => string;
    syncPartialFailure: (failed: number) => string;
    syncFailed: string;
    dialogTitle: string;
    nameLabel: string;
    namePlaceholder: string;
    typeLabel: string;
    langLabel: string;
    settingsLabel: (label: string) => string;
    createError: string;
    saveBtn: string;
    cancelBtn: string;
    // Parser strategy (#670)
    parserStrategy: string;
    parserName: string;
    fallbackChain: string;
    extractionStatus: string;
    charCount: string;
    chunkCount: string;
    chunkCountEst: string;
    ocrNeeded: string;
    ocrPerformed: string;
    translationQuality: string;
    layoutBlocks: string;
    tableBlocks: string;
    figureBlocks: string;
    lastError: string;
    unknown: string;
    yes: string;
    no: string;
    parserSummary: string;
    documentsByParser: string;
    extractedCount: string;
    ocrCount: string;
    ocrDone: string;
    failedCount: string;
    avgCharCount: string;
    noParserData: string;
    parserDocuments: string;
    // Source Health Dashboard (#674)
    sourceHealth: {
      title: string;
      noSources: string;
      noSourcesBody: string;
      summaryTotal: string;
      summaryIndexed: string;
      summaryPending: string;
      summaryFailed: string;
      healthy: string;
      degraded: string;
      failed: string;
      noCheck: string;
      lastCheck: string;
      docCounts: string;
      issues: string;
      emptyChunks: string;
      missingContent: string;
      missingMetadata: string;
      missingTitle: string;
      ocrEligible: string;
      ocrMaybeNeeded: string;
      indexLag: string;
      error: string;
      noQaData: string;
      sourceName: string;
      healthStatus: string;
      runQa: string;
      viewDocuments: string;
      emptyState: string;
      emptyStateBody: string;
      actionReextract: string;
      actionContent: string;
      actionMetadata: string;
      actionTitle: string;
      actionOcr: string;
      actionLag: string;
    };
  };
  cmd: {
    ariaLabel: string;
    placeholder: string;
    hint: string;
    empty: string;
  };
  adminLdap: {
    title: string;
    subtitle: string;
    searchLabel: string;
    searchPlaceholder: string;
    searchBtn: string;
    searchingText: string;
    searchEmpty: string;
    searchError: string;
    colName: string;
    colDN: string;
    colExternalId: string;
    colActions: string;
    mapBtn: string;
    selectGroupLabel: string;
    selectGroupPlaceholder: string;
    createMappingBtn: string;
    existingMappings: string;
    noMappings: string;
    ephemeralNote: string;
    mappingNote: string;
    deleteMappingLabel: string;
    deleteMappingConfirm: (name: string) => string;
    mappingCreated: string;
    mappingDeleted: string;
    loadError: string;
    createError: string;
    deleteError: string;
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
    chat: "Chat",
    subscriptions: "Subscriptions",
    notifications: "Notifications",
    history: "History",
    expertise: "Expertise",
    admin: "Admin",
    settings: "Settings",
    sourceHealth: "Source Health",
    collapse: "Collapse navigation",
    expand: "Expand navigation",
    primary: "Primary navigation",
    unread: (n) => `${n} unread`,
    signOut: "Sign out",
  },
  app: {
    loadingApp: "Loading application",
    loadFailed: "Failed to load",
    loadFailedBody:
      "Could not connect to the server. Reload the page to try again.",
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
    signUp: "Sign up",
    signUpLink: "Don't have an account? Sign up",
    signUpTitle: "Create an account",
    displayName: "Display name",
    confirmPassword: "Confirm password",
    passwordMismatch: "Passwords do not match",
    duplicateEmail: "An account with this email already exists",
    signUpSuccess: "Account created. You are now signed in.",
    signInLink: "Already have an account? Sign in",
  },
  search: {
    title: "Search",
    button: "Search",
    modeGroup: "Search mode",
    modeHybrid: "Hybrid",
    modeKeyword: "Keyword",
    modeSemantic: "Semantic",
    resultCount: (n) => `${n.toLocaleString()} result${n !== 1 ? "s" : ""}`,
    resultApproximate: (n) => `~${n.toLocaleString()} result${n !== 1 ? "s" : ""}`,
    activeFilters: "Active filters",
    removeFilter: (label) => `Remove filter: ${label}`,
    resultsLabel: "Search results",
    unavailableTitle: "Search unavailable",
    unavailableBody:
      "The search backend is not reachable. Check the server and try again.",
    retry: "Retry",
    noResultsTitle: "No results found",
    noResultsBody:
      "No accessible documents match your query. Try different terms or remove filters.",
    emptyTitle: "Start searching",
    emptyBody: "Type a query above and press Enter or Search.",
    failedToast: "Search failed. Check that the backend is reachable.",
    keyboardHelp:
      "Use ↑/↓ or j/k to choose a result, Enter to open, Space to preview, and Esc to close preview.",
    updating: "Updating…",
    retrievalDegraded: "Search degraded — partial results",
    quickPreviewTitle: "Quick preview",
    openSelected: "Open document",
    closePreview: "Close preview",
    loadMore: "Load more results",
    loadingMore: "Loading more…",
    previewLabel: "Preview",
    preview: (title) => `Quick preview: ${title}`,
    whyThisResult: "Why this result?",
    savePassage: "Save passage",
    today: "Today",
    daysAgo: (n) => `${n}d ago`,
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
    includeOlderVersions: "Include older versions",
    sortBy: "Sort by",
    sortRelevance: "Relevance",
    sortUpdated: "Updated",
    sortCreated: "Created",
    advanced: "Advanced",
    extension: "Extension",
    tags: "Tags",
    source: "Source",
  },
  document: {
    notFoundTitle: "Document not found",
    notFoundBody:
      "This document may have been deleted or you may not have access.",
    tryAgain: "Try again",
    backToSearch: "Back to search",
    untitled: "Untitled document",
    requestTranslation: "Request translation",
    download: "Download",
    downloadText: "Download text",
    downloadTranslation: "Download translated",
    downloadError: "Download failed. The file may no longer be available.",
  },
  preview: {
    loading: "Loading…",
    preparing: "Preparing preview…",
    bodyUnavailable: "Preview body unavailable.",
    emailBodyLabel: "Email body",
    emailRegion: "Email preview",
    bodyView: "Body view",
    viewFormatted: "Formatted",
    viewText: "Text",
    showQuoted: "Show quoted text",
    subject: "Subject",
    from: "From",
    to: "To",
    cc: "CC",
    date: "Date",
    blockedImages: (n) =>
      n === 1
        ? "1 remote image was blocked to protect your privacy."
        : `${n} remote images were blocked to protect your privacy.`,
    attachments: (n) => (n === 1 ? "1 attachment" : `${n} attachments`),
    attachmentOf: "Attachment of:",
    sheetRegion: "Spreadsheet preview",
    sheetTabs: "Sheets",
    sheetTruncated: "Preview shows the first rows and columns. Download the file for the full sheet.",
    rerender: "Re-render",
  },
  insight: {
    tabSummary: "Summary",
    tabQa: "Q&A",
    tabChat: "Chat",
    tabRelated: "Related",
    tabAnnotations: "Annotations",
    tabComments: "Comments",
    tabSubscriptions: "Subscriptions",
    tabVersions: "Versions",
    tabDetails: "Details",
    versionLatest: "Latest",
    versionOlder: "Older version",
    versionBannerTitle: "A newer version of this document is available.",
    versionBannerLink: "View latest version",
    versionsLoading: "Loading…",
    versionsFailedTitle: "Failed to load version history",
    versionsFailedBody: "Could not reach the server.",
    versionsEmpty: "No version history available.",
    versionLabel: (n) => `Version ${n}`,
    summaryLoading: "Loading…",
    summaryFailedTitle: "Failed to load summary",
    summaryFailedBody: "Could not reach the server.",
    summaryEmptyTitle: "No summary",
    summaryEmptyBody: "AI summary not yet available for this document.",
    generatedBy: (model, date) => `Generated by ${model} · ${date}`,
    entities: "Entities",
    entitiesFailed: "Could not reach the server.",
    tags: "Tags",
    tagsFailed: "Could not reach the server.",
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
    subscriptionsBody:
      "Subscribe to alerts for this document. Coming in Phase 08e.",
    whyRelated: "Why related?",
    relationScore: (score) => `Relation score: ${score}`,
  },
  qa: {
    title: "Q&A",
    ask: "Ask",
    failedTitle: "Request failed",
    failedBody:
      "The Q&A service is not reachable. Check the server and try again.",
    emptyTitle: "Ask anything",
    emptyBody:
      "Type a question and press Ask. Answers are grounded in your accessible documents.",
    toastError: "Q&A request failed. Check that the backend is reachable.",
  },
  chat: {
    pageTitle: "Document Chat",
    newChat: "New Chat",
    startChat: "Start a chat",
    emptyTitle: "Ask questions about your documents.",
    emptyBody:
      "Answers are based only on documents you can access, with sources.",
    noChatsYet: "No chats yet.",
    loadChatsError: "Failed to load chats.",
    loadSessionError: "Failed to load chat.",
    deleteSession: "Delete chat",
    deleteError: "Failed to delete chat.",
    sendError: "Failed to send message. Please try again.",
    inputPlaceholder: "Ask a question…",
    send: "Send",
    groundingNote: "Based only on documents you can access.",
    sourcesHeading: "Sources",
    chattingWith: "Chatting with",
    scopeAll: "All accessible documents",
    scopeSingleDocument: "Single document",
    scopeSelectedDocuments: "Selected documents",
    scopeSelectedDocumentsCount: (n) => `${n} selected documents`,
    scopeSource: "Source",
    scopeFolder: "Folder",
    scopeSearchResults: "Search results",
    untitledDocument: "Untitled document",
    scopeSwitchLabel: "Change scope",
    askAboutSelected: "Ask about selected",
    retry: "Retry",
    starterHeading: "Try asking",
    openDocument: "Open document",
    saveToEvidencePack: "Save to evidence pack",
    saveEvidence: "Save evidence",
    evidenceClose: "Close",
    evidenceLoading: "Loading preview…",
    evidenceNotFound: "Document not found.",
    evidenceForbidden: "Access denied.",
    evidenceNoPreview: "No preview available.",
    evidenceOpenFullPage: "Open in full page",
    evidenceTabEvidence: "Evidence",
    evidenceTabSource: "Source",
    evidenceTabRetrieval: "Retrieval",
    evidenceTabActions: "Actions",
    evidenceChunkIndex: "Chunk",
    evidenceOriginalLanguage: "Language",
    evidenceTranslatedFrom: "Translated from",
    evidenceSourceId: "Source",
    evidencePageSection: "Location",
    evidenceRetrievalTrace: "Retrieval trace",
    evidenceRetrievalStages: "Pipeline stages",
    evidenceRetrievalCandidates: "Candidates",
    evidenceRetrievalNoTrace: "No retrieval trace available for this message.",
    evidenceRetrievalReranked: "Reranked",
    evidenceRetrievalDegraded: "Retrieval degraded",
    evidenceCopyCitation: "Copy citation",
    evidenceCopied: "Copied!",
    evidenceReportBadCitation: "Report problem",
    evidenceBackends: "Backends",
    evidenceFusedRank: "Fused rank",
    evidenceRerankerDelta: "Reranker rank",
    evidenceFinalContextRank: "Context position",
    evidenceRetrievalDegradedBackends: "Degraded backends",
    evidenceScopeFiltered: "Scope filtered",
    evidenceDedupCount: "Deduplicated",
    evidenceScoreThresholdFiltered: "Below threshold",
    evidenceRerankerDropped: "Reranker dropped",
    evidenceSourceHealth: "Source health",
    evidenceSourceHealthHealthy: "Healthy",
    evidenceSourceHealthDegraded: "Degraded",
    evidenceSourceHealthFailed: "Failed",
    evidenceSourceHealthUnknown: "Unknown",
    evidenceSourceHealthNoData: "No recent source health check available.",
    feedbackTypeCorrect: "Citation is correct",
    feedbackTypeWrongPassage: "Wrong passage",
    feedbackTypeWrongLocation: "Right document, wrong location",
    feedbackTypeMissingSource: "Missing better source",
    feedbackTypeUnsupported: "Claim not supported",
    feedbackTypePermission: "Permission concern",
    feedbackTypeOther: "Other",
    feedbackComment: "Additional comments (optional)",
    feedbackSubmit: "Submit",
    feedbackSubmitting: "Submitting…",
    feedbackSuccess: "Feedback submitted. Thank you.",
    feedbackError: "Failed to submit feedback.",
    feedbackDuplicate: "You already submitted feedback for this citation.",
    phaseSearching: "Searching documents",
    phaseReadingSources: "Reading sources",
    phaseGenerating: "Generating answer",
    translatedFrom: (lang) => `Translated from ${lang}`,
  },
  notifications: {
    title: "Notifications",
    loading: "Loading…",
    failedTitle: "Failed to load notifications",
    failedBody: "Could not reach the server.",
    emptyTitle: "No notifications",
    emptyBody:
      "You'll be notified here when documents match your subscriptions.",
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
    subtitle:
      "Find colleagues through document evidence. Results are not rankings or performance scores.",
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
    unavailableBody:
      "You do not have access to this document's collaboration notes.",
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
    colLastSync: "Last sync",
    colActions: "Actions",
    syncBtn: "Sync",
    testConnectionBtn: "Test",
    testConnectionOk: "Connection settings look valid.",
    testConnectionError: "Connection test failed.",
    neverSynced: "Never synced",
    syncStatusSuccess: "Success",
    syncStatusPartialFailure: "Partial failure",
    syncStatusFailed: "Failed",
    lastSynced: (value) => `Last run: ${value}`,
    syncResult: (enqueued, skipped, failed) =>
      `Indexed: ${enqueued}  Skipped: ${skipped}  Failed: ${failed}`,
    syncStarted: (name) => `Sync started for ${name}.`,
    syncCompleted: (enqueued, skipped, failed) =>
      `Sync completed. Indexed ${enqueued} document${enqueued !== 1 ? "s" : ""}. Skipped ${skipped}. Failed ${failed}.`,
    syncPartialFailure: (failed) =>
      `Sync completed with failures. ${failed} document${failed !== 1 ? "s" : ""} failed. Check the source configuration.`,
    syncFailed: "Sync failed. Check the source configuration or retry later.",
    dialogTitle: "Add Source",
    nameLabel: "Name",
    namePlaceholder: "e.g. Legal Documents",
    typeLabel: "Type",
    langLabel: "Source language",
    settingsLabel: (label) => `${label} settings`,
    createError: "Failed to create source.",
    saveBtn: "Save Source",
    cancelBtn: "Cancel",
    // Parser strategy (#670)
    parserStrategy: "Parser Strategy",
    parserName: "Parser",
    fallbackChain: "Fallback chain",
    extractionStatus: "Extraction",
    charCount: "Chars",
    chunkCount: "Chunks",
    chunkCountEst: "Chunks (est.)",
    ocrNeeded: "OCR needed",
    ocrPerformed: "OCR done",
    translationQuality: "Translation",
    layoutBlocks: "Layout blocks",
    tableBlocks: "Tables",
    figureBlocks: "Figures",
    lastError: "Last error",
    unknown: "Unknown",
    yes: "Yes",
    no: "No",
    parserSummary: "Summary",
    documentsByParser: "Documents by parser",
    extractedCount: "Extracted",
    ocrCount: "OCR needed",
    ocrDone: "OCR done",
    failedCount: "Failed",
    avgCharCount: "Avg chars",
    noParserData: "No parser data available yet.",
    parserDocuments: "Documents",
    // Source Health Dashboard (#674)
    sourceHealth: {
      title: "Source Health",
      noSources: "No sources configured",
      noSourcesBody:
        "Add a source from the Sources page to start monitoring health.",
      summaryTotal: "Total",
      summaryIndexed: "Indexed",
      summaryPending: "Pending",
      summaryFailed: "Failed",
      healthy: "Healthy",
      degraded: "Degraded",
      failed: "Failed",
      noCheck: "No checks run",
      lastCheck: "Last check",
      docCounts: "Indexed / Pending / Failed",
      issues: "Issues",
      emptyChunks: "Empty chunks",
      missingContent: "Missing content",
      missingMetadata: "Missing metadata",
      missingTitle: "Missing title",
      ocrEligible: "OCR-eligible",
      ocrMaybeNeeded: "May need OCR",
      indexLag: "Index lag",
      error: "Failed to load source health data.",
      noQaData: "No QA data available yet.",
      sourceName: "Source",
      healthStatus: "Health",
      runQa: "Run QA check",
      viewDocuments: "View documents",
      emptyState: "No QA checks have been run yet.",
      emptyStateBody:
        "Click a source\u2019s \u201cRun QA check\u201d button to run diagnostics.",
      actionReextract:
        "Re-run extraction on affected documents.",
      actionContent:
        "Check document payloads or re-run extraction.",
      actionMetadata:
        "Re-run enrichment on affected documents.",
      actionTitle:
        "Edit document title or re-run extraction.",
      actionOcr:
        "Enable OCR processing or re-process affected documents.",
      actionLag:
        "Check pipeline worker status and retry configuration.",
    },
  },
  cmd: {
    ariaLabel: "Command menu",
    placeholder: "Type a destination…",
    hint: "Visible navigation remains available in the rail. Use this shortcut for faster routing.",
    empty: "No matching destinations.",
  },
  adminLdap: {
    title: "LDAP Group Mappings",
    subtitle:
      "Search LDAP groups live and map them to Tomorrowland groups. Only explicit mappings are persisted — LDAP groups are never used directly in document ACLs.",
    searchLabel: "Search LDAP groups",
    searchPlaceholder: "Search by group name or description…",
    searchBtn: "Search",
    searchingText: "Searching…",
    searchEmpty: "No LDAP groups found matching your query.",
    searchError: "LDAP search failed. Check the LDAP configuration.",
    colName: "Display Name",
    colDN: "Distinguished Name",
    colExternalId: "External ID",
    colActions: "Actions",
    mapBtn: "Map to Group",
    selectGroupLabel: "Target Tomorrowland Group",
    selectGroupPlaceholder: "Select a group…",
    createMappingBtn: "Create Mapping",
    existingMappings: "Existing Mappings",
    noMappings: "No explicit mappings configured yet.",
    ephemeralNote:
      "Search results are ephemeral — only groups you explicitly map are persisted.",
    mappingNote:
      "LDAP groups only grant Tomorrowland group membership through explicit mappings. Unmapped LDAP groups are ignored.",
    deleteMappingLabel: "Delete mapping",
    deleteMappingConfirm: (name: string) =>
      `Delete the mapping for "${name}"? This does not delete the Tomorrowland group itself.`,
    mappingCreated: "Mapping created.",
    mappingDeleted: "Mapping deleted.",
    loadError: "Failed to load mappings.",
    createError: "Failed to create mapping.",
    deleteError: "Failed to delete mapping.",
  },
  lang: {
    label: "Language",
    en: "English",
    he: "עברית",
  },
};
