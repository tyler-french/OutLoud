const dropZone = document.getElementById('drop-zone');
const urlInput = document.getElementById('url-input');
const fileInput = document.getElementById('file-input');
const itemsList = document.getElementById('items-list');
const voiceSelect = document.getElementById('voice');
const filterAll = document.getElementById('filter-all');
const filterDone = document.getElementById('filter-done');
const playerBar = document.getElementById('player-bar');
const audioPlayer = document.getElementById('audio-player');
const currentTitle = document.getElementById('current-title');
const closePlayer = document.getElementById('close-player');
const previewBtn = document.getElementById('preview-voice');

let previewAudio = null;

// Polling interval for status updates
let pollInterval = null;

// Start polling if there are items being processed
function startPolling() {
    if (pollInterval) return;
    pollInterval = setInterval(pollStatus, 2000);
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

// Check if any items need polling
function hasProcessingItems() {
    const items = itemsList.querySelectorAll('.item');
    for (const item of items) {
        const stage = item.dataset.stage;
        if (stage && !['ready', 'completed', 'error'].includes(stage)) {
            return true;
        }
    }
    return false;
}

// Poll for status updates
async function pollStatus() {
    try {
        const response = await fetch('/articles/status');
        const articles = await response.json();

        for (const article of articles) {
            updateItemInList(article);
        }

        // Stop polling if nothing is processing
        if (!hasProcessingItems()) {
            stopPolling();
        }
    } catch (error) {
        console.error('Polling error:', error);
    }
}

// Update an item in the list
function updateItemInList(article) {
    const item = itemsList.querySelector(`[data-id="${article.id}"]`);
    if (!item) {
        // New item, add it
        addItemToList(article);
        return;
    }

    const currentStage = item.dataset.stage;
    if (currentStage === article.processing_stage) {
        return; // No change
    }

    // Update the item
    item.dataset.stage = article.processing_stage || 'ready';
    item.dataset.status = article.status;

    // Update classes
    item.classList.toggle('done', article.status === 'completed');
    item.classList.toggle('error', article.processing_stage === 'error');

    // Update stage display
    const stageEl = item.querySelector('.item-stage');
    if (stageEl) {
        stageEl.textContent = article.processing_stage || 'ready';
        stageEl.className = `item-stage stage-${article.processing_stage || 'ready'}`;
    }

    // Update title if changed
    const titleEl = item.querySelector('.item-title');
    if (titleEl && titleEl.textContent !== article.title) {
        titleEl.textContent = article.title;
    }

    // Update error display
    let errorEl = item.querySelector('.item-error');
    if (article.error) {
        if (!errorEl) {
            errorEl = document.createElement('span');
            errorEl.className = 'item-error';
            item.querySelector('.item-info').appendChild(errorEl);
        }
        errorEl.textContent = article.error.substring(0, 30) + '...';
        errorEl.title = article.error;
    } else if (errorEl) {
        errorEl.remove();
    }

    // Update controls
    updateItemControls(item, article);
}

function updateItemControls(item, article) {
    const controls = item.querySelector('.item-controls');
    const stage = article.processing_stage || 'ready';

    // Clear existing buttons
    controls.innerHTML = '';

    if (stage === 'ready' && article.mp3_path) {
        const playBtn = document.createElement('button');
        playBtn.className = 'play-btn';
        playBtn.textContent = 'Play';
        playBtn.onclick = () => playItem(article.id);
        controls.appendChild(playBtn);

        if (article.status !== 'completed') {
            const doneBtn = document.createElement('button');
            doneBtn.className = 'done-btn';
            doneBtn.textContent = 'Done';
            doneBtn.onclick = () => markDone(article.id);
            controls.appendChild(doneBtn);
        }
    }

    if (stage === 'error') {
        const retryBtn = document.createElement('button');
        retryBtn.className = 'retry-btn';
        retryBtn.textContent = 'Retry';
        retryBtn.onclick = () => retryItem(article.id);
        controls.appendChild(retryBtn);
    }

    const newDeleteBtn = document.createElement('button');
    newDeleteBtn.className = 'delete-btn';
    newDeleteBtn.textContent = 'X';
    newDeleteBtn.onclick = () => deleteItem(article.id);
    controls.appendChild(newDeleteBtn);
}

dropZone.addEventListener('click', (e) => {
    if (e.target !== urlInput) {
        fileInput.click();
    }
});

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');

    const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.pdf'));
    if (files.length > 0) {
        uploadFiles(files);
    }
});

// File input change - batch upload
fileInput.addEventListener('change', (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
        uploadFiles(files);
    }
    fileInput.value = '';
});

urlInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        const url = urlInput.value.trim();
        if (url) {
            processUrl(url);
            urlInput.value = '';
        }
    }
});

urlInput.addEventListener('click', (e) => {
    e.stopPropagation();
});

// Batch upload PDFs
async function uploadFiles(files) {
    try {
        const formData = new FormData();
        for (const file of files) {
            formData.append('files', file);
        }
        formData.append('voice', voiceSelect.value);

        const response = await fetch('/import/pdfs', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (data.error) {
            alert('Error: ' + data.error);
            return;
        }

        // Refresh the list
        await pollStatus();
        startPolling();

    } catch (error) {
        alert('Upload failed: ' + error.message);
    }
}

async function processUrl(url) {
    try {
        const response = await fetch('/process/url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, voice: voiceSelect.value })
        });
        const data = await response.json();

        if (data.error) {
            alert('Error: ' + data.error);
            return;
        }

        // Refresh and start polling
        await pollStatus();
        startPolling();

    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// Add item to list
function addItemToList(article) {
    const existing = itemsList.querySelector(`[data-id="${article.id}"]`);
    if (existing) {
        updateItemInList(article);
        return;
    }

    const stage = article.processing_stage || 'ready';
    const div = document.createElement('div');
    div.className = 'item';
    if (article.status === 'completed') div.classList.add('done');
    if (stage === 'error') div.classList.add('error');

    div.dataset.id = article.id;
    div.dataset.status = article.status;
    div.dataset.stage = stage;

    div.innerHTML = `
        <div class="item-info">
            <span class="item-title">${article.title}</span>
            <span class="item-stage stage-${stage}">${stage}</span>
            ${article.error ? `<span class="item-error" title="${article.error}">${article.error.substring(0, 30)}...</span>` : ''}
        </div>
        <div class="item-controls"></div>
    `;

    updateItemControls(div, article);
    itemsList.insertBefore(div, itemsList.firstChild);
}

async function playItem(id) {
    const response = await fetch(`/article/${id}`);
    const article = await response.json();

    currentTitle.textContent = article.title;
    audioPlayer.src = `/audio/${id}`;
    playerBar.classList.remove('hidden');
    audioPlayer.play();
}

async function markDone(id) {
    await fetch(`/complete/${id}`, { method: 'PUT' });

    const item = itemsList.querySelector(`[data-id="${id}"]`);
    if (item) {
        item.classList.add('done');
        item.dataset.status = 'completed';
        const doneBtn = item.querySelector('.done-btn');
        if (doneBtn) doneBtn.remove();
    }
}

// Retry failed item
async function retryItem(id) {
    try {
        await fetch(`/article/${id}/reprocess`, { method: 'POST' });
        await pollStatus();
        startPolling();
    } catch (error) {
        alert('Retry failed: ' + error.message);
    }
}

// Delete item
async function deleteItem(id) {
    if (!confirm('Delete this item?')) return;

    await fetch(`/article/${id}`, { method: 'DELETE' });

    const item = itemsList.querySelector(`[data-id="${id}"]`);
    if (item) item.remove();
}

filterAll.addEventListener('click', () => {
    filterAll.classList.add('active');
    filterDone.classList.remove('active');
    itemsList.classList.remove('filter-done');
});

filterDone.addEventListener('click', () => {
    filterDone.classList.add('active');
    filterAll.classList.remove('active');
    itemsList.classList.add('filter-done');
});

closePlayer.addEventListener('click', () => {
    audioPlayer.pause();
    playerBar.classList.add('hidden');
});

previewBtn.addEventListener('click', () => {
    const voice = voiceSelect.value;

    if (previewAudio) {
        previewAudio.pause();
        previewAudio = null;
    }

    previewBtn.disabled = true;
    previewBtn.textContent = '...';

    const audio = new Audio(`/preview/voice/${voice}`);
    previewAudio = audio;

    audio.oncanplaythrough = () => {
        if (previewAudio !== audio) {
            return;
        }
        previewBtn.disabled = false;
        previewBtn.textContent = '\u25B6';
        audio.play();
    };

    audio.onended = () => {
        if (previewAudio !== audio) {
            return;
        }
        previewBtn.textContent = '\u25B6';
    };

    audio.onerror = () => {
        if (previewAudio !== audio) {
            return;
        }
        previewBtn.disabled = false;
        previewBtn.textContent = '\u25B6';
        console.error('Preview failed to load');
    };
});

// Start polling on page load if there are processing items
if (hasProcessingItems()) {
    startPolling();
}
