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
    addChatMessage: (role: string, text: string, metadata?: any, modelInfo?: any) => void;
    handleAddFromBubble: (entry: any) => void;

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
                SHOW_MODEL_INFO: string;
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
            data: string | null;
            mimeType: string | null;
            generationMode: boolean;
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
            textAvailability: ModelAvailability | null;
            multimodalAvailability: ModelAvailability | null;
            imageGenerationAvailability: ModelAvailability | null;
        };
        debug: {
            enabled: boolean;
            serverMode: boolean;
            showModelInfo: boolean;
            apiHistory: any[];
            lastBackendLogs: any;
            lastModelList: any;
            lastAllLogs: any;
        };
        defaultPrompt: string;
    };
}

/**
 * モデル利用可否情報
 */
interface ModelAvailability {
    available: boolean;
    model: string;
    error?: string;
}

/**
 * /api/models レスポンス型
 * バックエンド (endpoints.py get_models) のレスポンス構造に対応
 * フロントエンドで data.xxx を参照する際の型安全性を保証
 */
interface ModelsApiResponse {
    all: any[];
    text_only: any[];
    vision_capable: any[];
    image_generation_capable: any[];
    default_text_model: string;
    default_multimodal_model: string;
    text_availability: ModelAvailability;
    multimodal_availability: ModelAvailability;
    image_generation_availability: ModelAvailability;
    warnings?: Array<{ message: string }>;
}

/**
 * /api/config レスポンス型
 */
interface ConfigApiResponse {
    configs: any[];
    debug_mode: boolean;
    default_system_prompt: string;
}

/**
 * /api/chat レスポンス型
 */
interface ChatApiResponse {
    message: string;
    properties?: Record<string, any>;
    model: string;
    usage?: {
        prompt_tokens?: number;
        completion_tokens?: number;
        total_tokens?: number;
        completion_tokens_details?: {
            thinking_tokens?: number;
            reasoning_tokens?: number;
        };
        cached_tokens_details?: {
            thinking_tokens?: number;
        };
    };
    cost?: number;
    metadata?: {
        image_properties?: { title?: string; content?: string };
        image_base64?: string;
    };
    image_base64?: string;  // Image generation: returned at top level
    model_selection?: {  // Model selection transparency
        requested: string;
        used: string;
        fallback_occurred: boolean;
    };
    thinking?: string;  // AI reasoning/thinking steps (debug)
    raw_error?: string;  // Error details when generation fails
}

/**
 * /api/save レスポンス型
 */
interface SaveApiResponse {
    status: string;
    url: string;
}

/**
 * /api/targets レスポンス型
 */
interface TargetsApiResponse {
    targets: Array<{ id: string; type: 'database' | 'page'; title: string }>;
}

/**
 * /api/schema レスポンス型
 */
interface SchemaApiResponse {
    type: 'database' | 'page';
    schema: Record<string, any>;
}

/**
 * /api/pages/create レスポンス型
 */
interface CreatePageApiResponse {
    id: string;
    title: string;
    type: string;
}
