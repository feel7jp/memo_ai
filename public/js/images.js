// ========== IMAGES MODULE ==========
// 画像処理・カメラ撮影・プレビュー機能

/**
 * Compress image using Canvas API
 * Reduces file size significantly while maintaining quality for AI analysis
 */
export function compressImage(file, maxDimension = 600, quality = 0.7) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        
        reader.onload = (e) => {
            const img = new Image();
            
            img.onload = () => {
                // Calculate new dimensions
                let width = img.width;
                let height = img.height;
                
                if (width > maxDimension || height > maxDimension) {
                    if (width > height) {
                        height = Math.round((height * maxDimension) / width);
                        width = maxDimension;
                    } else {
                        width = Math.round((width * maxDimension) / height);
                        height = maxDimension;
                    }
                }
                

                
                // Create canvas and compress
                const canvas = document.createElement('canvas');
                canvas.width = width;
                canvas.height = height;
                
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);
                
                // Convert to JPEG base64
                const dataUrl = canvas.toDataURL('image/jpeg', quality);
                const matches = dataUrl.match(/^data:(.+);base64,(.+)$/);
                
                if (matches && matches.length === 3) {
                    resolve({
                        mimeType: matches[1],
                        base64: matches[2],
                        dataUrl: dataUrl
                    });
                } else {
                    reject(new Error('Failed to compress image'));
                }
            };
            
            img.onerror = () => reject(new Error('Failed to load image'));
            img.src = /** @type {string} */(e.target.result);
        };
        
        reader.onerror = () => reject(new Error('Failed to read file'));
        reader.readAsDataURL(file);
    });
}

/**
 * Capture photo from camera using getUserMedia API (for desktop)
 * Creates a temporary modal with live camera preview and capture button
 */
export async function capturePhotoFromCamera() {
    const updateState = window.updateState;
    const showToast = window.showToast;
    
    return new Promise(async (resolve, reject) => {
        let stream = null;
        
        try {
            // Request camera access
            updateState('📷', 'カメラへのアクセスを要求中...', { step: 'requesting_camera' });
            stream = await navigator.mediaDevices.getUserMedia({ 
                video: { facingMode: 'user' },
                audio: false 
            });
            
            // Create modal with video preview
            const modal = document.createElement('div');
            modal.className = 'modal';
            modal.style.display = 'flex';
            modal.innerHTML = `
                <div class="modal-content" style="max-width: 600px;">
                    <div class="modal-header">
                        <h2>📷 カメラ</h2>
                        <button class="close-btn" id="closeCameraModal">×</button>
                    </div>
                    <div class="modal-body">
                        <video id="cameraPreview" autoplay playsinline style="width: 100%; border-radius: 8px; background: black;"></video>
                        <canvas id="cameraCanvas" style="display: none;"></canvas>
                    </div>
                    <div class="modal-footer">
                        <button class="btn-secondary" id="cancelCamera">キャンセル</button>
                        <button class="btn-primary" id="capturePhoto">📸 撮影</button>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            
            /** @type {HTMLVideoElement} */
            const video = /** @type {any} */(document.getElementById('cameraPreview'));
            /** @type {HTMLCanvasElement} */
            const canvas = /** @type {any} */(document.getElementById('cameraCanvas'));
            const captureBtn = document.getElementById('capturePhoto');
            const cancelBtn = document.getElementById('cancelCamera');
            const closeBtn = document.getElementById('closeCameraModal');
            
            // Start video stream
            video.srcObject = stream;
            
            updateState('✅', 'カメラ準備完了', { step: 'camera_ready' });
            
            const cleanup = () => {
                if (stream) {
                    stream.getTracks().forEach(track => track.stop());
                }
                document.body.removeChild(modal);
                const stateDisplay = document.getElementById('stateDisplay');
                if (stateDisplay) stateDisplay.classList.add('hidden');
            };
            
            // Capture button handler
            captureBtn.addEventListener('click', async () => {
                try {
                    updateState('📸', '写真を撮影中...', { step: 'capturing' });
                    
                    // Set canvas dimensions to match video
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    
                    // Draw current frame to canvas
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(video, 0, 0);
                    
                    // Convert to blob and compress
                    canvas.toBlob(async (blob) => {
                        try {
                            // Convert blob to file
                            const file = new File([blob], 'camera-photo.jpg', { type: 'image/jpeg' });
                            
                            // Compress the image
                            const { base64, mimeType } = await compressImage(file);
                            
                            // Set preview
                            window.setPreviewImage(base64, mimeType);
                            
                            cleanup();
                            updateState('✅', '写真を保存しました', { step: 'saved' });
                            showToast("写真を撮影しました");
                            setTimeout(() => {
                                const stateDisplay = document.getElementById('stateDisplay');
                                if (stateDisplay) stateDisplay.classList.add('hidden');
                            }, 2000);
                            
                            resolve();
                        } catch (err) {
                            cleanup();
                            reject(err);
                        }
                    }, 'image/jpeg', 0.9);
                    
                } catch (err) {
                    cleanup();
                    reject(err);
                }
            });
            
            // Cancel/Close handlers
            const handleCancel = () => {
                cleanup();
                resolve(); // Not an error, just cancelled
            };
            
            cancelBtn.addEventListener('click', handleCancel);
            closeBtn.addEventListener('click', handleCancel);
            
        } catch (err) {
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
            }
            
            // Translate common errors
            const error = /** @type {Error} */(err);
            let errorMsg = error.message;
            if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
                errorMsg = 'カメラへのアクセスが拒否されました';
            } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
                errorMsg = 'カメラが見つかりませんでした';
            } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
                errorMsg = 'カメラは別のアプリケーションで使用中です';
            }
            
            updateState('❌', 'カメラアクセスに失敗', { step: 'error', error: errorMsg });
            setTimeout(() => {
                const stateDisplay = document.getElementById('stateDisplay');
                if (stateDisplay) stateDisplay.classList.add('hidden');
            }, 3000);
            
            reject(new Error(errorMsg));
        }
    });
}

export function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = /** @type {string} */(reader.result); // data:image/jpeg;base64,...
            // Extract core base64 and mime type
            const matches = result.match(/^data:(.+);base64,(.+)$/);
            if (matches && matches.length === 3) {
                resolve({
                    mimeType: matches[1],
                    base64: matches[2],
                    dataUrl: result
                });
            } else {
                reject(new Error("Invalid format"));
            }
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

/**
 * Update visibility of the shared attachment area based on children
 */
function updateAttachmentAreaVisibility() {
    const attachmentArea = document.getElementById('imageAttachmentArea');
    const previewArea = document.getElementById('imagePreviewArea');
    const genTagArea = document.getElementById('imageGenTagArea');
    if (!attachmentArea) return;

    const hasPreview = previewArea && !previewArea.classList.contains('hidden');
    const hasGenTag = genTagArea && !genTagArea.classList.contains('hidden');

    if (hasPreview || hasGenTag) {
        attachmentArea.classList.remove('hidden');
    } else {
        attachmentArea.classList.add('hidden');
    }
}

export function setPreviewImage(base64, mimeType) {

    window.App.image.data = base64;
    window.App.image.mimeType = mimeType;
    
    const previewArea = document.getElementById('imagePreviewArea');
    /** @type {HTMLImageElement} */
    const previewImg = /** @type {any} */(document.getElementById('imagePreview'));
    
    previewImg.src = `data:${mimeType};base64,${base64}`;
    previewArea.classList.remove('hidden');
    updateAttachmentAreaVisibility();

}

export function clearPreviewImage() {

    window.App.image.data = null;
    window.App.image.mimeType = null;
    
    const previewArea = document.getElementById('imagePreviewArea');
    /** @type {HTMLImageElement} */
    const previewImg = /** @type {any} */(document.getElementById('imagePreview'));
    
    previewImg.src = '';
    if (previewArea) {
        previewArea.classList.add('hidden');
    }
    updateAttachmentAreaVisibility();
    
    window.debugLog('🗑️ Image preview cleared');
}

/**
 * 画像生成モードを有効化
 */
export function enableImageGenMode() {
    window.App.image.generationMode = true;
    
    const genTagArea = document.getElementById('imageGenTagArea');
    if (genTagArea) {
        genTagArea.classList.remove('hidden');
    }
    updateAttachmentAreaVisibility();
    
    window.debugLog('🎨 Image generation mode enabled');
}

/**
 * 画像生成モードを無効化
 */
export function disableImageGenMode() {
    window.App.image.generationMode = false;
    
    const genTagArea = document.getElementById('imageGenTagArea');
    if (genTagArea) {
        genTagArea.classList.add('hidden');
    }
    updateAttachmentAreaVisibility();
    
    window.debugLog('🗑️ Image generation mode disabled');
}

/**
 * Setup image-related event handlers
 * Called from main.js during initialization
 */
export function setupImageHandlers() {
    const showToast = window.showToast;
    const setLoading = window.setLoading;
    
    // DOM Elements matches index.html
    const addMediaBtn = document.getElementById('addMediaBtn');
    const mediaMenu = document.getElementById('mediaMenu');
    const cameraBtn = document.getElementById('cameraBtn');
    const galleryBtn = document.getElementById('galleryBtn');
    
    // Hidden inputs
    /** @type {HTMLInputElement} */
    const imageInput = /** @type {any} */(document.getElementById('imageInput')); // For Gallery
    /** @type {HTMLInputElement} */
    const cameraInput = /** @type {any} */(document.getElementById('cameraInput')); // For Mobile Camera
    
    // 1. Toggle Media Menu
    if (addMediaBtn && mediaMenu) {
        addMediaBtn.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent document click from closing immediately
            mediaMenu.classList.toggle('hidden');
        });
        
        // Close menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!addMediaBtn.contains(/** @type {Node} */(e.target)) && !mediaMenu.contains(/** @type {Node} */(e.target))) {
                mediaMenu.classList.add('hidden');
            }
        });
    } else {
        console.error('[Images] Required elements (addMediaBtn or mediaMenu) not found');
    }
    
    // 2. Library/Gallery Handler
    if (galleryBtn && imageInput) {
        galleryBtn.addEventListener('click', () => {
            imageInput.click();
            if (mediaMenu) mediaMenu.classList.add('hidden');
        });
        
        imageInput.addEventListener('change', async (e) => {
            const file = /** @type {HTMLInputElement} */(e.target).files[0];
            if (!file) return;
            
            try {
                setLoading(true, '画像処理中...');
                const { base64, mimeType } = await compressImage(file);
                setPreviewImage(base64, mimeType);
            } catch (err) {
                console.error('Image processing failed:', err);
                showToast('画像の処理に失敗しました');
            } finally {
                setLoading(false);
                imageInput.value = ''; // Reset
            }
        });
    }
    
    // 3. Camera Handler
    // Prioritize desktop custom camera modal if available, otherwise use mobile input
    // However, index.html has capture="user" input for mobile.
    // Let's use the custom camera modal for desktop experience as it was implemented in capturePhotoFromCamera
    if (cameraBtn) {
        cameraBtn.addEventListener('click', () => {
             if (mediaMenu) mediaMenu.classList.add('hidden');
             
             // Check if mobile device (simple check)
             const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
             
             if (isMobile && cameraInput) {
                 // Use native mobile camera input
                 cameraInput.click();
             } else {
                 // Use desktop modal
                 capturePhotoFromCamera();
             }
        });
    }
    
    // Handle mobile camera input changes
    if (cameraInput) {
        cameraInput.addEventListener('change', async (e) => {
            const file = /** @type {HTMLInputElement} */(e.target).files[0];
            if (!file) return;
            
            try {
                setLoading(true, '画像処理中...');
                const { base64, mimeType } = await compressImage(file);
                setPreviewImage(base64, mimeType);
            } catch (err) {
                console.error('Camera processing failed:', err);
                showToast('画像の処理に失敗しました');
            } finally {
                setLoading(false);
                cameraInput.value = ''; // Reset
            }
        });
    }

    // 4. Remove Image Handler
    const removeImageBtn = document.getElementById('removeImageBtn');
    if (removeImageBtn) {
        removeImageBtn.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent bubbling
            clearPreviewImage();
            
            // Reset inputs to allow selecting the same file again
            // Note: imageInput and cameraInput are defined in the closure of setupImageHandlers
            if (imageInput) imageInput.value = '';
            if (cameraInput) cameraInput.value = '';
        });
    }
    
    // 5. Image Generation Button Handler
    const imageGenBtn = document.getElementById('imageGenBtn');
    if (imageGenBtn) {
        imageGenBtn.addEventListener('click', () => {
            enableImageGenMode();
            if (mediaMenu) mediaMenu.classList.add('hidden');
           showToast('画像生成モードを有効にしました');
        });
    }
    
    // 6. Remove Image Generation Tag Handler
    const removeImageGenBtn = document.getElementById('removeImageGenBtn');
    if (removeImageGenBtn) {
        removeImageGenBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            disableImageGenMode();
        });
    }

}
