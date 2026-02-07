/**
 * Type declarations for Memo AI application
 * This file provides TypeScript definitions for window globals and DOM elements
 */

// Extend Window interface with custom global functions
interface Window {
    // Debug functions
    openDebugModal: () => void;
    closeDebugModal: () => void;
    loadDebugInfo: () => void;
    copyApiHistory: () => void;
    copyApiEntry: (jsonString: string) => void;
    recordApiCall: (endpoint: string, method: string, request: any, response: any, error: string | null, status: number | null) => void;
    debugLog: (...args: any[]) => void;
    copyModelList: () => void;

    // Image functions
    capturePhotoFromCamera: () => Promise<void>;
    setPreviewImage: (base64: string, mimeType: string) => void;
    clearPreviewImage: () => void;
    compressImage: (file: File, maxSizeMB?: number) => Promise<string>;

    // Chat functions
    sendStamp: (emoji: string) => void;
    showAITypingIndicator: () => void;
    hideAITypingIndicator: () => void;
    addChatMessage: (role: string, text: string, metadata?: any) => void;
    handleAddFromBubble: (content: string) => void;

    // Prompt functions
    openPromptModal: () => void;
    closePromptModal: () => void;
    saveSystemPrompt: () => void;
    resetSystemPrompt: () => void;
    showDiscardConfirmation: () => void;

    // Model functions
    loadAvailableModels: () => Promise<void>;
    openModelModal: () => void;
    renderModelList: () => void;
    selectTempModel: (modelId: string) => void;
    saveModelSelection: () => void;
    closeModelModal: () => void;

    // Main app functions
    showToast: (msg: string) => void;
    setLoading: (isLoading: boolean, text?: string) => void;
    showState: () => void;
    updateState: (icon: string, message: string, details?: any) => void;
    fetchWithCache: (url: string, cacheKey: string, ttl?: number) => Promise<any>;
    loadTargets: (forceRefresh?: boolean) => Promise<void>;
    refreshTargetList: () => void;
    handleTargetChange: (skipRefreshOrEvent?: boolean | Event) => Promise<void>;
    fetchAndTruncatePageContent: (pageId: string, type: string) => Promise<string | null>;
    handleDirectSave: () => Promise<void>;
    saveToDatabase: () => Promise<void>;
    saveToPage: () => Promise<void>;
    openContentModal: () => void;
    openNewPageModal: () => void;
    createNewPage: (title: string) => Promise<void>;
    handleSuperReload: () => void;
    toggleSettingsMenu: () => void;
    fillForm: (data: any) => void;
    handleSessionClear: () => void;

    // Global App state
    App: {
        cache: {
            KEYS: {
                TARGETS: string;
                PAGE_CONTENT_PREFIX: string;
                CHAT_HISTORY: string;
                PROMPT_PREFIX: string;
            };
            TTL: {
                TARGETS: number;
                PAGE_CONTENT: number;
            };
        };
        target: {
            id: string | null;
            type: 'database' | 'page' | null;
            schema: any;
            systemPrompt: string | null;
        };
        chat: {
            history: any[];
            session: any[];
            isComposing: boolean;
        };
        image: {
            base64: string | null;
            mimeType: string | null;
        };
        model: {
            allModels: any[];
            available: any[];
            textOnly: any[];
            vision: any[];
            defaultText: string | null;
            defaultMultimodal: string | null;
            current: string | null;
            tempSelected: string | null;
            showAllModels: boolean;
            sessionCost: number;
        };
        debug: {
            enabled: boolean;
            serverMode: boolean;
            showModelInfo: boolean;
            apiHistory: any[];
            lastBackendLogs: any;
            lastModelList: any;
        };
        defaultPrompt: string;
    };
}
