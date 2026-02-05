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
                
                console.log(`[Image Compress] Original: ${img.width}x${img.height}, Compressed: ${width}x${height}`);
                
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
            img.src = e.target.result;
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
            
            const video = document.getElementById('cameraPreview');
            const canvas = document.getElementById('cameraCanvas');
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
            let errorMsg = err.message;
            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                errorMsg = 'カメラへのアクセスが拒否されました';
            } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                errorMsg = 'カメラが見つかりませんでした';
            } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
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
            const result = reader.result; // data:image/jpeg;base64,...
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

export function setPreviewImage(base64, mimeType) {
    console.log('[Preview] Setting preview image, mime:', mimeType, 'size:', base64.length, 'chars');
    window.App.image.base64 = base64;
    window.App.image.mimeType = mimeType;
    
    const previewArea = document.getElementById('imagePreviewArea');
    const previewImg = document.getElementById('previewImg');
    
    previewImg.src = `data:${mimeType};base64,${base64}`;
    previewArea.classList.remove('hidden');
    console.log('[Preview] Preview area shown');
}

export function clearPreviewImage() {
    console.log('[Preview] Clearing preview image');
    window.App.image.base64 = null;
    window.App.image.mimeType = null;
    
    const previewArea = document.getElementById('imagePreviewArea');
    const previewImg = document.getElementById('previewImg');
    
    previewImg.src = '';
    previewArea.classList.add('hidden');
}

/**
 * Setup image-related event handlers
 * Called from main.js during initialization
 */
export function setupImageHandlers() {
    const showToast = window.showToast;
    const setLoading = window.setLoading;
    
    const mediaBtn = document.getElementById('mediaBtn');
    const mediaInput = document.getElementById('mediaInput');
    const captureBtn = document.getElementById('captureBtn');
    
    if (mediaBtn && mediaInput) {
        mediaBtn.addEventListener('click', () => {
            mediaInput.click();
        });
        
        mediaInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
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
                mediaInput.value = ''; // Reset
            }
        });
    }
    
    if (captureBtn) {
        captureBtn.addEventListener('click', () => {
            capturePhotoFromCamera();
        });
    }
    
    console.log('[Images] Event handlers initialized');
}
