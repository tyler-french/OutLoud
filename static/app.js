// DOM Elements
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
const processingPanel = document.getElementById('processing-panel');
const processingList = document.getElementById('processing-list');

// Processing queue
const processingItems = new Map();

// Drop zone - click to select files
dropZone.addEventListener('click', (e) => {
    if (e.target !== urlInput) {
        fileInput.click();
    }
});

// Drag and drop
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
    files.forEach(file => processFile(file));
});

// File input change
fileInput.addEventListener('change', (e) => {
    Array.from(e.target.files).forEach(file => processFile(file));
    fileInput.value = '';
});

// URL input - Enter to submit
urlInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        const url = urlInput.value.trim();
        if (url) {
            processUrl(url);
            urlInput.value = '';
        }
    }
});

// Prevent URL input click from triggering file picker
urlInput.addEventListener('click', (e) => {
    e.stopPropagation();
});

// Process a PDF file
async function processFile(file) {
    const tempId = 'temp-' + Date.now() + Math.random().toString(36).substr(2, 9);
    addProcessingItem(tempId, file.name);

    try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('voice', voiceSelect.value);

        const response = await fetch('/process/pdf', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (data.error) throw new Error(data.error);

        // Start listening for progress
        listenToProgress(data.task_id, tempId, file.name);

    } catch (error) {
        updateProcessingItem(tempId, 'Error: ' + error.message, 0);
        setTimeout(() => removeProcessingItem(tempId), 3000);
    }
}

// Process a URL
async function processUrl(url) {
    const tempId = 'temp-' + Date.now();
    const displayName = new URL(url).hostname;
    addProcessingItem(tempId, displayName);

    try {
        const response = await fetch('/process/url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, voice: voiceSelect.value })
        });
        const data = await response.json();

        if (data.error) throw new Error(data.error);

        listenToProgress(data.task_id, tempId, displayName);

    } catch (error) {
        updateProcessingItem(tempId, 'Error: ' + error.message, 0);
        setTimeout(() => removeProcessingItem(tempId), 3000);
    }
}

// Listen to SSE progress
function listenToProgress(taskId, tempId, name) {
    const eventSource = new EventSource(`/process/progress/${taskId}`);

    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.error) {
            eventSource.close();
            updateProcessingItem(tempId, 'Error: ' + data.error, 0);
            setTimeout(() => removeProcessingItem(tempId), 3000);
            return;
        }

        if (data.done) {
            eventSource.close();
            removeProcessingItem(tempId);
            addItemToList(data.article);
            return;
        }

        // Update progress
        const percent = data.percent || 0;
        const status = data.status || 'Processing...';
        updateProcessingItem(tempId, status, percent);
    };

    eventSource.onerror = () => {
        eventSource.close();
        updateProcessingItem(tempId, 'Connection lost', 0);
        setTimeout(() => removeProcessingItem(tempId), 3000);
    };
}

// Processing panel management
function addProcessingItem(id, name) {
    processingItems.set(id, { name, status: 'Starting...', percent: 0 });
    updateProcessingPanel();
}

function updateProcessingItem(id, status, percent) {
    if (processingItems.has(id)) {
        processingItems.get(id).status = status;
        processingItems.get(id).percent = percent;
        updateProcessingPanel();
    }
}

function removeProcessingItem(id) {
    processingItems.delete(id);
    updateProcessingPanel();
}

function updateProcessingPanel() {
    if (processingItems.size === 0) {
        processingPanel.classList.add('hidden');
        return;
    }

    processingPanel.classList.remove('hidden');
    processingList.innerHTML = '';

    processingItems.forEach((item, id) => {
        const div = document.createElement('div');
        div.className = 'processing-item';
        div.innerHTML = `
            <div class="name">${item.name}</div>
            <div class="status">${item.status}</div>
            <div class="progress-bar-mini">
                <div class="fill" style="width: ${item.percent}%"></div>
            </div>
        `;
        processingList.appendChild(div);
    });
}

// Add completed item to list
function addItemToList(article) {
    const existing = itemsList.querySelector(`[data-id="${article.id}"]`);
    if (existing) {
        existing.remove();
    }

    const div = document.createElement('div');
    div.className = 'item' + (article.status === 'completed' ? ' done' : '');
    div.dataset.id = article.id;
    div.dataset.status = article.status;
    div.innerHTML = `
        <div class="item-info">
            <span class="item-title">${article.title}</span>
            <span class="item-status">${article.status}</span>
        </div>
        <div class="item-controls">
            ${article.mp3_path ? `<button class="play-btn" onclick="playItem(${article.id})">Play</button>` : ''}
            ${article.status !== 'completed' && article.mp3_path ? `<button class="done-btn" onclick="markDone(${article.id})">Done</button>` : ''}
            <button class="delete-btn" onclick="deleteItem(${article.id})">X</button>
        </div>
    `;
    itemsList.insertBefore(div, itemsList.firstChild);
}

// Play item
async function playItem(id) {
    const response = await fetch(`/article/${id}`);
    const article = await response.json();

    currentTitle.textContent = article.title;
    audioPlayer.src = `/audio/${id}`;
    playerBar.classList.remove('hidden');
    audioPlayer.play();
}

// Mark as done
async function markDone(id) {
    await fetch(`/complete/${id}`, { method: 'PUT' });

    const item = itemsList.querySelector(`[data-id="${id}"]`);
    if (item) {
        item.classList.add('done');
        item.dataset.status = 'completed';
        item.querySelector('.item-status').textContent = 'completed';
        const doneBtn = item.querySelector('.done-btn');
        if (doneBtn) doneBtn.remove();
    }
}

// Delete item
async function deleteItem(id) {
    if (!confirm('Delete this item?')) return;

    await fetch(`/article/${id}`, { method: 'DELETE' });

    const item = itemsList.querySelector(`[data-id="${id}"]`);
    if (item) item.remove();
}

// Filter toggle
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

// Close player
closePlayer.addEventListener('click', () => {
    audioPlayer.pause();
    playerBar.classList.add('hidden');
});
