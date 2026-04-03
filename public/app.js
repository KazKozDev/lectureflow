/**
 * Timecoder Frontend Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    if (typeof marked !== 'undefined') {
        marked.setOptions({
            gfm: true,
            breaks: false,
        });
    }

    // Elements
    const providerSelect = document.getElementById('providerSelect');
    const modelSelect = document.getElementById('modelSelect');
    const languageSelect = document.getElementById('languageSelect');
    const analyzeForm = document.getElementById('analyzeForm');
    const analyzeBtn = document.getElementById('analyzeBtn');

    const loadingState = document.getElementById('loadingState');
    const loadingStatusText = document.getElementById('loadingStatusText');
    const loadingProgressBar = document.getElementById('loadingProgressBar');
    const loadingProgressValue = document.getElementById('loadingProgressValue');
    const errorState = document.getElementById('errorState');
    const resultsContainer = document.getElementById('resultsContainer');
    const errorTitle = document.getElementById('errorTitle');
    const errorMessage = document.getElementById('errorMessage');
    const markdownOutput = document.getElementById('markdownOutput');
    const resultStats = document.getElementById('resultStats');
    const videoPlayerPanel = document.getElementById('videoPlayerPanel');
    const videoPlayerFrame = document.getElementById('videoPlayerFrame');
    const pinCurrentVideoBtn = document.getElementById('pinCurrentVideoBtn');
    const pinnedVideosList = document.getElementById('pinnedVideosList');
    const youtubeVideosList = document.getElementById('youtubeVideosList');
    const analysisSearchBar = document.getElementById('analysisSearchBar');
    const transcriptSearchInput = document.getElementById('transcriptSearchInput');
    const transcriptSearchMeta = document.getElementById('transcriptSearchMeta');
    const historyList = document.getElementById('historyList');
    const historyCount = document.getElementById('historyCount');
    const isPlaylist = document.getElementById('isPlaylist');
    const useCache = document.getElementById('useCache');
    
    // Exports
    const copyBtn = document.getElementById('copyBtn');
    const exportJsonBtn = document.getElementById('exportJsonBtn');
    const exportSrtBtn = document.getElementById('exportSrtBtn');
    const exportYtBtn = document.getElementById('exportYtBtn');
    
    // Tabs & Chat
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    const chatForm = document.getElementById('chatForm');
    const chatInput = document.getElementById('chatInput');
    const chatMessages = document.getElementById('chatMessages');

    let currentRawData = null;
    let currentRenderedMode = null;
    let currentAnalysisUrl = '';
    let libraryVideos = [];
    const analysisCache = new Map();
    let autoModeSwitchInFlight = false;
    const PINNED_VIDEOS_KEY = 'timecoder-pinned-videos';

    const escapeHtml = (value) => String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');

    const formatTimestamp = (seconds) => {
        const totalSeconds = Math.max(0, Math.floor(Number(seconds) || 0));
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const secs = totalSeconds % 60;
        if (hours > 0) {
            return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
        }
        return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    };

    const buildYouTubeTimestampUrl = (url, seconds) => {
        if (!url) return '#';
        try {
            const parsed = new URL(url);
            parsed.searchParams.set('t', `${Math.max(0, Math.floor(Number(seconds) || 0))}s`);
            return parsed.toString();
        } catch (e) {
            return url;
        }
    };

    const buildYouTubeEmbedUrl = (videoId, seconds = 0) => {
        if (!videoId) return '';
        const start = Math.max(0, Math.floor(Number(seconds) || 0));
        const params = new URLSearchParams({
            rel: '0',
            modestbranding: '1',
            playsinline: '1'
        });
        if (start > 0) {
            params.set('start', String(start));
        }
        return `https://www.youtube-nocookie.com/embed/${videoId}?${params.toString()}`;
    };

    const updateVideoPlayer = (seconds = 0) => {
        if (!videoPlayerPanel || !videoPlayerFrame) return;
        const videoId = currentRawData?.video_id;
        if (!videoId) {
            videoPlayerPanel.classList.add('hidden');
            videoPlayerFrame.src = '';
            return;
        }
        videoPlayerPanel.classList.remove('hidden');
        videoPlayerFrame.src = buildYouTubeEmbedUrl(videoId, seconds);
    };

    const highlightMatch = (text, query) => {
        const safeText = escapeHtml(text);
        if (!query) return safeText;
        const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const matcher = new RegExp(`(${escapedQuery})`, 'ig');
        return safeText.replace(matcher, '<mark class="transcript-highlight">$1</mark>');
    };

    const clearAnalysisSearchHighlights = () => {
        if (!markdownOutput) return;
        markdownOutput.querySelectorAll('mark.markdown-search-hit').forEach((mark) => {
            const parent = mark.parentNode;
            if (!parent) return;
            parent.replaceChild(document.createTextNode(mark.textContent || ''), mark);
            parent.normalize();
        });
    };

    const applyAnalysisSearch = (query = '') => {
        clearAnalysisSearchHighlights();

        if (!analysisSearchBar || !transcriptSearchMeta) return;

        if (currentRenderedMode !== 'detailed') {
            analysisSearchBar.classList.add('hidden');
            transcriptSearchMeta.textContent = 'Search is available in Detailed Conspectus';
            return;
        }

        analysisSearchBar.classList.remove('hidden');

        const segments = Array.isArray(currentRawData?.segments) ? currentRawData.segments : [];
        const trimmedQuery = query.trim();

        if (!trimmedQuery) {
            transcriptSearchMeta.textContent = segments.length
                ? `Search inside ${segments.length} transcript segments`
                : 'Find words directly in the conspectus';
            return;
        }

        if (!markdownOutput) {
            transcriptSearchMeta.textContent = 'Analysis is not ready yet.';
            return;
        }

        const escapedQuery = trimmedQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const matcher = new RegExp(escapedQuery, 'gi');
        const textNodes = [];
        const walker = document.createTreeWalker(markdownOutput, NodeFilter.SHOW_TEXT, {
            acceptNode(node) {
                const parent = node.parentElement;
                if (!parent) return NodeFilter.FILTER_REJECT;
                if (!node.nodeValue || !node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
                if (['SCRIPT', 'STYLE', 'TEXTAREA', 'INPUT', 'MARK'].includes(parent.tagName)) {
                    return NodeFilter.FILTER_REJECT;
                }
                return NodeFilter.FILTER_ACCEPT;
            }
        });

        let currentNode = walker.nextNode();
        while (currentNode) {
            textNodes.push(currentNode);
            currentNode = walker.nextNode();
        }

        let matchCount = 0;
        let firstMatch = null;

        textNodes.forEach((node) => {
            const text = node.nodeValue;
            if (!text) return;

            matcher.lastIndex = 0;
            if (!matcher.test(text)) {
                matcher.lastIndex = 0;
                return;
            }

            matcher.lastIndex = 0;
            const fragment = document.createDocumentFragment();
            let lastIndex = 0;
            let match = matcher.exec(text);

            while (match) {
                const start = match.index;
                const end = start + match[0].length;

                if (start > lastIndex) {
                    fragment.appendChild(document.createTextNode(text.slice(lastIndex, start)));
                }

                const mark = document.createElement('mark');
                mark.className = 'markdown-search-hit';
                mark.textContent = text.slice(start, end);
                fragment.appendChild(mark);

                if (!firstMatch) firstMatch = mark;
                matchCount += 1;
                lastIndex = end;
                match = matcher.exec(text);
            }

            if (lastIndex < text.length) {
                fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
            }

            node.parentNode.replaceChild(fragment, node);
        });

        transcriptSearchMeta.textContent = matchCount
            ? `${matchCount} matches in analysis`
            : 'Nothing found. Try another word or phrase.';

        if (firstMatch) {
            firstMatch.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    };

    const parseQaPairs = (rawText) => {
        const lines = String(rawText || '').split(/\r?\n/);
        const pairs = [];
        let currentQuestion = '';
        let currentAnswer = '';
        let state = '';

        const cleanLabel = (line) => line
            .replace(/^\s*[-*+]\s*/, '')
            .replace(/^\s*\d+[.)]\s*/, '')
            .replace(/^\s*\*\*/, '')
            .replace(/\*\*\s*$/, '')
            .trim();

        const pushPair = () => {
            const q = currentQuestion.trim();
            const a = currentAnswer.trim();
            if (q && a) {
                pairs.push({ question: q, answer: a });
            }
            currentQuestion = '';
            currentAnswer = '';
            state = '';
        };

        for (const originalLine of lines) {
            const line = cleanLabel(originalLine);
            if (!line) {
                if (state === 'a' && currentAnswer) currentAnswer += '\n';
                continue;
            }

            const qMatch = line.match(/^Q:\s*(.+)$/i);
            if (qMatch) {
                pushPair();
                currentQuestion = qMatch[1].trim();
                state = 'q';
                continue;
            }

            const aMatch = line.match(/^A:\s*(.+)$/i);
            if (aMatch) {
                currentAnswer = aMatch[1].trim();
                state = 'a';
                continue;
            }

            if (state === 'q') {
                currentQuestion += ` ${line}`;
            } else if (state === 'a') {
                currentAnswer += `${currentAnswer.endsWith('\n') ? '' : ' '}${line}`;
            }
        }

        pushPair();
        return pairs;
    };

    const injectTimestampLinks = (html) => String(html || '').replace(
        /(\[(\d{2}:\d{2})(?:\s*[-–]\s*(\d{2}:\d{2}))?\])/g,
        (match, label, startTime) => `<a href="#" class="timestamp-link" data-timestamp="${startTime}">${label}</a>`
    );

    const parseTimestampToSeconds = (value) => {
        if (!value) return 0;
        const parts = String(value).split(':').map((part) => Number(part));
        if (parts.some((part) => Number.isNaN(part))) return 0;
        if (parts.length === 2) {
            return (parts[0] * 60) + parts[1];
        }
        if (parts.length === 3) {
            return (parts[0] * 3600) + (parts[1] * 60) + parts[2];
        }
        return 0;
    };

    const splitLongParagraphHtml = (paragraph) => {
        const html = paragraph.innerHTML || '';
        const text = paragraph.textContent || '';
        const normalized = text.replace(/\s+/g, ' ').trim();
        if (!normalized || (normalized.length < 420)) return [];

        // Walk through text nodes and insert <br><br> after every ~3 sentences
        const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
        const splits = [];
        let sentenceCount = 0;
        let node;

        while ((node = walker.nextNode())) {
            const matches = [...node.textContent.matchAll(/[.!?]+\s+/g)];
            for (const m of matches) {
                sentenceCount++;
                if (sentenceCount >= 3) {
                    splits.push({ node, offset: m.index + m[0].length });
                    sentenceCount = 0;
                }
            }
        }

        if (!splits.length) return [];

        // Insert splits in reverse order to preserve offsets
        for (let i = splits.length - 1; i >= 0; i--) {
            const { node: targetNode, offset } = splits[i];
            const after = targetNode.splitText(offset);
            const br1 = document.createElement('br');
            const br2 = document.createElement('br');
            after.parentNode.insertBefore(br2, after);
            after.parentNode.insertBefore(br1, br2);
        }

        return splits;
    };

    const refineDetailedConspectusLayout = () => {
        if (!markdownOutput || currentRenderedMode !== 'detailed') return;

        markdownOutput.querySelectorAll('h1, h2, h3').forEach((heading) => {
            if (heading.classList.contains('detailed-heading-ready')) return;
            const timestamp = heading.querySelector('.timestamp-link');
            if (!timestamp) return;

            const titleText = heading.textContent.replace(timestamp.textContent || '', '').trim();
            heading.innerHTML = '';

            const meta = document.createElement('span');
            meta.className = 'detailed-heading-meta';
            meta.appendChild(timestamp);

            const title = document.createElement('span');
            title.className = 'detailed-heading-title';
            title.textContent = titleText;

            heading.appendChild(meta);
            heading.appendChild(title);
            heading.classList.add('detailed-heading-ready');
        });

        markdownOutput.querySelectorAll('p').forEach((paragraph) => {
            if (paragraph.closest('li, td, th, blockquote')) return;
            if (paragraph.querySelector('img, table, iframe')) return;
            if (paragraph.classList.contains('detailed-paragraph-ready')) return;

            splitLongParagraphHtml(paragraph);
            paragraph.classList.add('detailed-paragraph-ready');
        });
    };

    const getPinnedVideos = () => {
        try {
            const raw = localStorage.getItem(PINNED_VIDEOS_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch (e) {
            return [];
        }
    };

    const setPinnedVideos = (items) => {
        localStorage.setItem(PINNED_VIDEOS_KEY, JSON.stringify(items));
    };

    const isPinnedVideo = (videoId) => getPinnedVideos().some((item) => item.video_id === videoId);

    const togglePinnedVideo = (video) => {
        const items = getPinnedVideos();
        const exists = items.some((item) => item.video_id === video.video_id);
        const next = exists
            ? items.filter((item) => item.video_id !== video.video_id)
            : [
                {
                    video_id: video.video_id,
                    url: video.url,
                    title: video.title || video.video_id,
                    thumbnail_url: video.thumbnail_url || `https://i.ytimg.com/vi/${video.video_id}/hqdefault.jpg`,
                },
                ...items,
            ].slice(0, 12);
        setPinnedVideos(next);
        updatePinCurrentButton();
        renderPinnedVideos();
    };

    const updatePinCurrentButton = () => {
        if (!pinCurrentVideoBtn || !currentRawData?.video_id) return;
        const pinned = isPinnedVideo(currentRawData.video_id);
        pinCurrentVideoBtn.textContent = pinned ? 'Pinned' : 'Pin';
        pinCurrentVideoBtn.classList.toggle('is-pinned', pinned);
    };

    const renderVideoCard = (video, options = {}) => {
        const tagsHtml = Array.isArray(video.shared_keywords) && video.shared_keywords.length
            ? `<div class="video-suggestion-tags">${video.shared_keywords.map((tag) => `<span class="video-suggestion-tag">${escapeHtml(tag)}</span>`).join('')}</div>`
            : '';
        const pinActive = isPinnedVideo(video.video_id);
        return `
            <article class="video-suggestion-card" data-video-id="${escapeHtml(video.video_id)}" data-video-url="${escapeHtml(video.url || '')}" data-video-title="${escapeHtml(video.title || video.video_id)}" data-video-thumbnail="${escapeHtml(video.thumbnail_url || '')}">
                <img class="video-suggestion-thumb" src="${escapeHtml(video.thumbnail_url || `https://i.ytimg.com/vi/${video.video_id}/hqdefault.jpg`)}" alt="${escapeHtml(video.title || video.video_id)}">
                <div class="video-suggestion-body">
                    <div class="video-suggestion-title">${escapeHtml(video.title || video.video_id)}</div>
                    <div class="video-suggestion-meta">${escapeHtml(options.meta || '')}</div>
                    ${tagsHtml}
                    <div class="video-suggestion-actions">
                        <button type="button" class="video-side-btn" data-action="open-video">Open</button>
                        <button type="button" class="video-side-btn ${pinActive ? 'is-pinned' : ''}" data-action="toggle-pin">${pinActive ? 'Pinned' : 'Pin'}</button>
                    </div>
                </div>
            </article>
        `;
    };

    let lastYouTubeVideos = [];

    const renderPinnedVideos = () => {
        if (!pinnedVideosList) return;
        const items = getPinnedVideos();
        if (!items.length) {
            pinnedVideosList.innerHTML = '<div class="video-card-empty">Pin videos here to keep them close.</div>';
            return;
        }
        pinnedVideosList.innerHTML = items.map((video) => renderVideoCard(video, { meta: 'Pinned by you' })).join('');
    };

    const renderYouTubeVideos = (items, configured = true) => {
        if (!youtubeVideosList) return;
        lastYouTubeVideos = Array.isArray(items) ? items : [];
        if (!configured) {
            youtubeVideosList.innerHTML = '<div class="video-card-empty">Add a YouTube Data API key in Settings to load external recommendations.</div>';
            return;
        }
        if (!lastYouTubeVideos.length) {
            youtubeVideosList.innerHTML = '<div class="video-card-empty">No YouTube recommendations found for this video yet.</div>';
            return;
        }
        youtubeVideosList.innerHTML = lastYouTubeVideos
            .map((video) => renderVideoCard(video, { meta: video.channel_title || 'YouTube recommendation' }))
            .join('');
    };

    const loadYouTubeRecommendations = async () => {
        if (!currentRawData?.video_id || !youtubeVideosList) return;
        try {
            const response = await fetch(`/api/videos/${currentRawData.video_id}/youtube-recommendations?limit=6`);
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || 'Failed to load YouTube recommendations');
            renderYouTubeVideos(result.data || [], Boolean(result.configured));
        } catch (e) {
            console.error(e);
            renderYouTubeVideos([], true);
        }
    };

    const normalizeVideoUrl = (url) => (url || '').trim();
    const getCurrentCacheContext = () => ({
        provider: providerSelect ? (providerSelect.value || '') : '',
        model: modelSelect ? (modelSelect.value || '') : '',
        language: languageSelect ? (languageSelect.value || 'Auto') : 'Auto'
    });
    const buildCacheKey = (url, mode, context = getCurrentCacheContext()) =>
        `${normalizeVideoUrl(url)}::${mode}::${context.provider}::${context.model}::${context.language}`;
    const buildCachePrefix = (url) => `timecoder-analysis:${normalizeVideoUrl(url)}::`;

    const persistCachedResult = (url, mode, data) => {
        if (!url || !mode || !data) return;
        const key = buildCacheKey(url, mode);
        analysisCache.set(key, data);
        try {
            localStorage.setItem(`timecoder-analysis:${key}`, JSON.stringify(data));
        } catch (e) {
            console.warn('Failed to persist analysis cache', e);
        }
    };

    const loadCachedResult = (url, mode) => {
        const key = buildCacheKey(url, mode);
        if (analysisCache.has(key)) {
            return analysisCache.get(key);
        }

        try {
            const raw = localStorage.getItem(`timecoder-analysis:${key}`);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            analysisCache.set(key, parsed);
            return parsed;
        } catch (e) {
            console.warn('Failed to read analysis cache', e);
            return null;
        }
    };

    const hasAnyCachedResult = (url) => {
        const normalized = normalizeVideoUrl(url);
        if (!normalized) return false;

        for (const key of analysisCache.keys()) {
            if (key.startsWith(`${normalized}::`)) {
                return true;
            }
        }

        try {
            const prefix = buildCachePrefix(normalized);
            for (let i = 0; i < localStorage.length; i += 1) {
                const key = localStorage.key(i);
                if (key && key.startsWith(prefix)) {
                    return true;
                }
            }
        } catch (e) {
            console.warn('Failed to inspect analysis cache', e);
        }

        return false;
    };

    const renderAnalysisResult = (data, mode) => {
        currentRawData = data;
        currentRenderedMode = mode;
        resultStats.textContent = `${data.segment_count} segments processed`;
        if (markdownOutput) {
            markdownOutput.classList.toggle('is-detailed-mode', mode === 'detailed');
        }

        let mdText = data.markdown;

        if (mode === 'flashcards') {
            const pairs = parseQaPairs(mdText);
            if (pairs.length) {
                mdText = `<div class="flashcards-grid">\n` +
                    pairs.map(({ question, answer }) => {
                        const qHtml = typeof marked !== 'undefined' ? marked.parseInline(question.trim()) : question.trim();
                        const aHtml = typeof marked !== 'undefined' ? marked.parse(answer.trim()) : answer.trim();
                        return `<div class="flashcard">
                                            <div class="flashcard-q"><strong>Q:</strong> ${qHtml}</div>
                                            <div class="flashcard-a"><strong>A:</strong> ${aHtml}</div>
                                         </div>`;
                    }).join('') +
                    `\n</div>`;
            }
        }

        if (mode === 'quiz') {
            const pairs = parseQaPairs(mdText);
            if (pairs.length) {
                let index = 0;
                mdText = `<div class="quiz-shell">
                            <div class="quiz-topbar">
                                <div>
                                    <div class="quiz-eyebrow">Self-check quiz</div>
                                    <h3 class="quiz-title">Test yourself on the video</h3>
                                </div>
                                <div class="quiz-counter">${pairs.length} questions</div>
                            </div>
                            <div class="quiz-grid">\n` +
                    pairs.map(({ question, answer }) => {
                        index += 1;
                        const answerId = `quiz-answer-${index}`;
                        const inputId = `quiz-input-${index}`;
                        const qHtml = typeof marked !== 'undefined' ? marked.parseInline(question.trim()) : question.trim();
                        const aHtml = typeof marked !== 'undefined' ? marked.parse(answer.trim()) : answer.trim();
                        return `<div class="quiz-card">
                                    <div class="quiz-meta">
                                        <span class="quiz-number">Question ${index}</span>
                                        <span class="quiz-status">Try first</span>
                                    </div>
                                    <div class="quiz-question">${qHtml}</div>
                                    <label class="quiz-response" for="${inputId}">
                                        <span>Your answer</span>
                                        <textarea id="${inputId}" placeholder="Write your answer before checking..."></textarea>
                                    </label>
                                    <button type="button" class="quiz-toggle" data-answer-id="${answerId}">Check Answer</button>
                                    <div class="quiz-answer hidden" id="${answerId}">
                                        <div class="quiz-answer-label">Correct answer</div>
                                        <div class="quiz-answer-body">${aHtml}</div>
                                    </div>
                                </div>`;
                    }).join('') +
                    `\n</div></div>`;
            }
        }

        if (typeof marked !== 'undefined') {
            markdownOutput.innerHTML = ((mode === 'flashcards' && mdText.includes('flashcards-grid')) || (mode === 'quiz' && mdText.includes('quiz-grid')))
                ? mdText
                : injectTimestampLinks(marked.parse(mdText));
        } else {
            markdownOutput.innerText = data.markdown;
        }

        refineDetailedConspectusLayout();

        updateVideoPlayer();
        applyAnalysisSearch(transcriptSearchInput ? transcriptSearchInput.value : '');
        loadYouTubeRecommendations();
        loadHistory();
        updatePinCurrentButton();
        renderPinnedVideos();

        setState('success');
    };

    const updateLoadingProgress = (progress = 0, message = '') => {
        const value = Math.max(0, Math.min(100, Math.round(Number(progress) || 0)));
        if (loadingProgressBar) loadingProgressBar.style.width = `${value}%`;
        if (loadingProgressValue) loadingProgressValue.textContent = `${value}%`;
        if (loadingStatusText && message) loadingStatusText.textContent = message;
    };

    const analyzePayload = (url, mode, useCache) => ({
        url: url,
        mode: mode,
        use_cache: useCache,
        skip_llm: false,
        provider: providerSelect ? providerSelect.value : null,
        model_name: modelSelect ? modelSelect.value : null,
        language: languageSelect ? languageSelect.value : 'Auto'
    });

    const runClassicAnalysis = async (url, mode, useCache) => {
        updateLoadingProgress(12, 'Submitting analysis request...');
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(analyzePayload(url, mode, useCache))
        });

        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.detail || 'Analysis failed on the server');
        }
        updateLoadingProgress(100, 'Analysis complete.');
        return result.data;
    };

    // Toast functionality
    const showToast = (message) => {
        let toast = document.querySelector('.toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.className = 'toast';
            document.body.appendChild(toast);
        }
        toast.textContent = message;
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 3000);
    };    // Settings Persistence
    const saveSettings = () => {
        const settings = {
            provider: providerSelect ? providerSelect.value : null,
            model: modelSelect ? modelSelect.value : null,
            language: languageSelect ? languageSelect.value : 'Auto',
            useCache: useCache ? useCache.checked : true,
            isPlaylist: isPlaylist ? isPlaylist.checked : false
        };
        localStorage.setItem('tc-settings', JSON.stringify(settings));
    };

    const loadSettings = () => {
        try {
            const raw = localStorage.getItem('tc-settings');
            if (!raw) return null;
            return JSON.parse(raw);
        } catch (e) {
            return null;
        }
    };

    let allAvailableModels = {};

    // Load Models on Startup
    const loadModels = async () => {
        try {
            const res = await fetch('/api/models');
            const result = await res.json();
            
            if (result.status === 'success' && result.data) {
                allAvailableModels = result.data;
                providerSelect.innerHTML = '';
                
                let firstProvider = null;
                for (const provider of Object.keys(allAvailableModels)) {
                    if (allAvailableModels[provider].length > 0) {
                        const option = document.createElement('option');
                        option.value = provider;
                        option.textContent = provider.charAt(0).toUpperCase() + provider.slice(1);
                        providerSelect.appendChild(option);
                        if (!firstProvider) firstProvider = provider;
                    }
                }

                const saved = loadSettings();
                if (saved && saved.provider && Object.keys(allAvailableModels).includes(saved.provider)) {
                    providerSelect.value = saved.provider;
                } else if (firstProvider) {
                    providerSelect.value = firstProvider;
                }
                
                populateModelSelect(providerSelect.value);
                
                if (saved && saved.model && [...modelSelect.options].some(o => o.value === saved.model)) {
                    modelSelect.value = saved.model;
                }
            }
        } catch (e) {
            console.error(e);
            providerSelect.innerHTML = '<option value="default" selected>Default</option>';
            modelSelect.innerHTML = '<option value="default" selected>Backend fallback</option>';
        }
    };
    
    const populateModelSelect = (provider) => {
        modelSelect.innerHTML = '';
        const models = allAvailableModels[provider] || [];
        models.forEach(modelName => {
            const option = document.createElement('option');
            option.value = modelName;
            option.textContent = modelName;
            modelSelect.appendChild(option);
        });
    };

    if (providerSelect) {
        providerSelect.addEventListener('change', (e) => {
            populateModelSelect(e.target.value);
            saveSettings();
        });
    }
    
    if (modelSelect) modelSelect.addEventListener('change', saveSettings);
    if (languageSelect) languageSelect.addEventListener('change', saveSettings);
    if (useCache) useCache.addEventListener('change', saveSettings);
    if (isPlaylist) isPlaylist.addEventListener('change', saveSettings);

    const savedGlobal = loadSettings();
    if (savedGlobal) {
        if (languageSelect && savedGlobal.language) languageSelect.value = savedGlobal.language;
        if (useCache && savedGlobal.useCache !== undefined) useCache.checked = savedGlobal.useCache;
        if (isPlaylist && savedGlobal.isPlaylist !== undefined) isPlaylist.checked = savedGlobal.isPlaylist;
    }

    loadModels();
    
    // History Panel Logic
    const loadHistory = async () => {
        if (!historyList) return;
        try {
            const res = await fetch('/api/videos');
            const data = await res.json();
            if (data.status === 'success') {
                const vids = data.data;
                libraryVideos = vids;
                historyCount.textContent = vids.length;
                historyList.innerHTML = '';
                
                vids.forEach(v => {
                    const item = document.createElement('div');
                    item.className = 'history-item';
                    
                    const icon = document.createElement('i');
                    icon.className = 'fa-brands fa-youtube';
                    icon.style.color = '#ff0000';
                    
                    const title = document.createElement('span');
                    title.className = 'history-title';
                    title.textContent = v.title || v.video_id;
                    title.title = v.title || v.video_id;
                    
                    const delBtn = document.createElement('button');
                    delBtn.className = 'btn-delete';
                    delBtn.title = 'Delete from Library';
                    delBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
                    
                    item.addEventListener('click', (e) => {
                        if (e.target.closest('.btn-delete')) return; 
                        document.getElementById('youtubeUrl').value = v.url;
                        document.getElementById('analyzeBtn').click();
                    });
                    
                    delBtn.addEventListener('click', async (e) => {
                        e.stopPropagation();
                        if (!confirm(`Delete ${title.textContent} from library?`)) return;
                        try {
                            const dr = await fetch(`/api/videos/${v.video_id}`, { method: 'DELETE' });
                            if (dr.ok) {
                                showToast('Video deleted');
                                loadHistory();
                            }
                        } catch (err) {
                            showToast('Failed to delete');
                        }
                    });
                    
                    item.appendChild(icon);
                    item.appendChild(title);
                    item.appendChild(delBtn);
                    historyList.appendChild(item);
                });
            }
        } catch (e) {
            console.error("Failed to load history", e);
        }
    };
    
    loadHistory();
    renderPinnedVideos();

    // UI State Management
    const setState = (state) => {
        loadingState.classList.add('hidden');
        errorState.classList.add('hidden');
        resultsContainer.classList.add('hidden');
        
        analyzeBtn.disabled = (state === 'loading');
        if (state !== 'loading') {
            updateLoadingProgress(0, 'Downloading transcript, segmenting context, and applying AI models.');
        }
        
        switch (state) {
            case 'loading':
                loadingState.classList.remove('hidden');
                break;
            case 'error':
                errorState.classList.remove('hidden');
                break;
            case 'success':
                resultsContainer.classList.remove('hidden');
                break;
            case 'idle':
            default:
                break;
        }
    };

    // Smart error display helper
    const showDetailedError = (errorMsg, extraContext = {}) => {
        const errorDetails = document.getElementById('errorDetails');
        const errorModelName = document.getElementById('errorModelName');
        const errorProviderName = document.getElementById('errorProviderName');
        const errorCodeValue = document.getElementById('errorCodeValue');
        const errorSuggestion = document.getElementById('errorSuggestion');
        const errorSuggestionText = document.getElementById('errorSuggestionText');

        const provider = extraContext.provider || (providerSelect ? providerSelect.value : '—');
        const model = extraContext.model || (modelSelect ? modelSelect.value : '—');

        errorModelName.textContent = model;
        errorProviderName.textContent = provider.charAt(0).toUpperCase() + provider.slice(1);

        // Parse error message for useful code
        let shortError = errorMsg;
        if (shortError.length > 120) shortError = shortError.substring(0, 117) + '...';
        errorCodeValue.textContent = shortError;
        errorCodeValue.title = errorMsg;

        errorDetails.classList.remove('hidden');

        // Generate smart suggestion based on error pattern
        let suggestion = '';
        const msg = errorMsg.toLowerCase();
        if (msg.includes('not a chat model') || msg.includes('not supported')) {
            suggestion = `Model "${model}" is not compatible with the Chat API. Select a different model like gpt-4o-mini or gpt-4.1.`;
        } else if (msg.includes('max_tokens') && msg.includes('max_completion_tokens')) {
            suggestion = `Model "${model}" requires a newer API parameter format. Please update the application or choose a legacy model (gpt-4o, gpt-4).`;
        } else if (msg.includes('rate limit') || msg.includes('429')) {
            suggestion = 'API rate limit exceeded. Wait a few minutes before retrying, or switch to a different provider.';
        } else if (msg.includes('authentication') || msg.includes('api key') || msg.includes('401') || msg.includes('invalid_api_key')) {
            suggestion = 'API key is invalid or missing. Go to Settings (gear icon in the sidebar) and verify your API key.';
        } else if (msg.includes('fetch') || msg.includes('network') || msg.includes('failed to fetch')) {
            suggestion = 'Could not connect to the server. Make sure the backend is running on port 8000.';
        } else if (msg.includes('transcript') || msg.includes('subtitles')) {
            suggestion = 'Could not extract video transcript. The video may have disabled subtitles. Whisper fallback may take longer.';
        } else {
            suggestion = 'Try a different model or provider. If this persists, check the server logs for details.';
        }

        errorSuggestionText.textContent = suggestion;
        errorSuggestion.classList.remove('hidden');
    };

    // Form Submission
    analyzeForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const url = document.getElementById('youtubeUrl').value;
        const mode = document.querySelector('input[name="mode"]:checked').value;
        const useCache = document.getElementById('useCache').checked;
        const isPlaylist = document.getElementById('isPlaylist').checked;
        
        if (!url) return;

        setState('loading');
        currentRawData = null;
        currentRenderedMode = null;
        currentAnalysisUrl = url;
        autoModeSwitchInFlight = false;

        if (isPlaylist) {
            const playlistProgressContainer = document.getElementById('playlistProgressContainer');
            const playlistStatus = document.getElementById('playlistStatus');
            const playlistProgressBar = document.getElementById('playlistProgressBar');
            
            loadingState.classList.add('hidden');
            playlistProgressContainer.classList.remove('hidden');
            
            try {
                const response = await fetch('/api/analyze/batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url: url,
                        mode: mode,
                        use_cache: useCache,
                        skip_llm: false,
                        provider: providerSelect ? providerSelect.value : null,
                        model_name: modelSelect ? modelSelect.value : null,
                        language: languageSelect ? languageSelect.value : 'Auto'
                    })
                });

                if (!response.ok) throw new Error('Failed to start batch processing');

                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value, { stream: true });
                    const lines = chunk.split('\n').filter(line => line.trim());
                    
                    for (const line of lines) {
                        try {
                            const data = JSON.parse(line);
                            if (data.type === 'info') {
                                playlistStatus.textContent = data.message;
                            } else if (data.type === 'progress') {
                                playlistStatus.textContent = `Processing video ${data.index} of ${data.total}`;
                                playlistProgressBar.style.width = `${(data.index / data.total) * 100}%`;
                            } else if (data.type === 'success') {
                                showToast(`Finished: ${data.video_id}`);
                            } else if (data.type === 'error') {
                                showToast(`Error on video: ${data.message}`);
                            } else if (data.type === 'done') {
                                playlistStatus.textContent = "Playlist complete! Check Library Chat.";
                                setTimeout(() => {
                                    playlistProgressContainer.classList.add('hidden');
                                    setState('idle');
                                }, 3000);
                            }
                        } catch (e) {
                            console.error("Parse error on json", line);
                        }
                    }
                }
            } catch (error) {
                console.error(error);
                errorTitle.textContent = "Playlist Error";
                errorMessage.textContent = error.message;
                showDetailedError(error.message);
                setState('error');
            }
            return;
        }

        try {
            let response = await fetch('/api/analyze/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(analyzePayload(url, mode, useCache))
            });

            if (response.status === 404) {
                const fallbackResult = await runClassicAnalysis(url, mode, useCache);
                if (fallbackResult.warning) {
                    errorTitle.textContent = "LLM Processing Failed";
                    errorMessage.textContent = "Transcript was extracted but the AI model could not process it.";
                    showDetailedError(fallbackResult.warning);
                    setState('error');
                    loadHistory();
                    return;
                }
                persistCachedResult(url, mode, fallbackResult);
                renderAnalysisResult(fallbackResult, mode);
                loadHistory();
                return;
            }

            if (!response.ok) {
                const result = await response.json().catch(() => ({}));
                throw new Error(result.detail || 'Analysis failed on the server');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let finalResult = null;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.trim()) continue;
                    const event = JSON.parse(line);
                    if (event.type === 'progress') {
                        updateLoadingProgress(event.progress, event.message);
                        continue;
                    }
                    if (event.type === 'error') {
                        throw new Error(event.detail || 'Analysis failed on the server');
                    }
                    if (event.type === 'result') {
                        finalResult = event.data;
                    }
                }
            }

            if (!finalResult) {
                throw new Error('Analysis finished without a result');
            }

            if (finalResult.warning) {
                errorTitle.textContent = "LLM Processing Failed";
                errorMessage.textContent = "Transcript was extracted but the AI model could not process it.";
                showDetailedError(finalResult.warning);
                setState('error');
                loadHistory();
                return;
            }

            persistCachedResult(url, mode, finalResult);
            renderAnalysisResult(finalResult, mode);
            loadHistory();
            
        } catch (error) {
            console.error(error);
            errorTitle.textContent = "Pipeline Error";
            errorMessage.textContent = error.message;
            showDetailedError(error.message);
            setState('error');
        }
    });

    // Copy Markdown to Clipboard
    copyBtn.addEventListener('click', () => {
        if (!currentRawData) return;
        navigator.clipboard.writeText(currentRawData.markdown)
            .then(() => showToast('Markdown copied to clipboard!'))
            .catch(() => showToast('Failed to copy.'));
    });

    // Generalized Export Function
    const handleExport = async (format, extension) => {
        if (!currentRawData) return;
        try {
            const response = await fetch(`/api/export/${currentRawData.video_id}?format=${format}`);
            if (!response.ok) throw new Error('Export failed');
            
            const text = await response.text();
            
            const blob = new Blob([text], { type: format === 'json' ? 'application/json' : 'text/plain' });
            const url = URL.createObjectURL(blob);
            
            const a = document.createElement('a');
            a.href = url;
            a.download = `timecoder_${currentRawData.video_id}.${extension}`;
            document.body.appendChild(a);
            a.click();
            
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            showToast(`${format.toUpperCase()} Exported!`);
        } catch (e) {
            console.error(e);
            showToast('Export error!');
        }
    };

    exportJsonBtn.addEventListener('click', () => handleExport('json', 'json'));
    exportSrtBtn.addEventListener('click', () => handleExport('srt', 'srt'));
    exportYtBtn.addEventListener('click', () => handleExport('youtube', 'txt'));

    if (transcriptSearchInput) {
        transcriptSearchInput.addEventListener('input', (e) => {
            applyAnalysisSearch(e.target.value || '');
        });
    }

    const handleVideoCardAction = (e) => {
        const actionBtn = e.target.closest('[data-action]');
        if (!actionBtn) return;
        const card = actionBtn.closest('.video-suggestion-card');
        if (!card) return;
        const video = {
            video_id: card.getAttribute('data-video-id') || '',
            url: card.getAttribute('data-video-url') || '',
            title: card.getAttribute('data-video-title') || '',
            thumbnail_url: card.getAttribute('data-video-thumbnail') || '',
        };

        if (actionBtn.getAttribute('data-action') === 'toggle-pin') {
            togglePinnedVideo(video);
            return;
        }

        if (actionBtn.getAttribute('data-action') === 'open-video' && video.url) {
            const youtubeUrlInput = document.getElementById('youtubeUrl');
            if (youtubeUrlInput) youtubeUrlInput.value = video.url;
            analyzeForm.requestSubmit();
        }
    };

    if (pinnedVideosList) pinnedVideosList.addEventListener('click', handleVideoCardAction);
    if (youtubeVideosList) youtubeVideosList.addEventListener('click', handleVideoCardAction);
    if (pinCurrentVideoBtn) {
        pinCurrentVideoBtn.addEventListener('click', () => {
            if (!currentRawData?.video_id) return;
            togglePinnedVideo({
                video_id: currentRawData.video_id,
                url: currentAnalysisUrl || document.getElementById('youtubeUrl')?.value || '',
                title: currentRawData.title || currentRawData.video_id,
                thumbnail_url: `https://i.ytimg.com/vi/${currentRawData.video_id}/hqdefault.jpg`,
            });
        });
    }

    if (markdownOutput) {
        markdownOutput.addEventListener('click', (e) => {
            const toggle = e.target.closest('.quiz-toggle');
            if (toggle) {
                const answerId = toggle.getAttribute('data-answer-id');
                const answer = answerId ? document.getElementById(answerId) : null;
                if (!answer) return;
                const quizCard = toggle.closest('.quiz-card');
                const status = quizCard ? quizCard.querySelector('.quiz-status') : null;
                const isHidden = answer.classList.contains('hidden');
                answer.classList.toggle('hidden', !isHidden);
                toggle.textContent = isHidden ? 'Hide Answer' : 'Check Answer';
                if (status) {
                    status.textContent = isHidden ? 'Answer shown' : 'Try first';
                }
                return;
            }

            const timestampLink = e.target.closest('.timestamp-link');
            if (timestampLink) {
                e.preventDefault();
                const seconds = parseTimestampToSeconds(timestampLink.getAttribute('data-timestamp'));
                updateVideoPlayer(seconds);
            }
        });
    }

    document.querySelectorAll('input[name="mode"]').forEach((input) => {
        input.addEventListener('change', (e) => {
            const labelStr = e.target.getAttribute('data-label') || 'Video';
            const analyzeBtnText = document.getElementById('analyzeBtnText');
            if (analyzeBtnText) analyzeBtnText.textContent = `Analyze ${labelStr}`;

            const url = document.getElementById('youtubeUrl').value;
            const mode = document.querySelector('input[name="mode"]:checked')?.value;

            if (!url || !mode) {
                return;
            }

            const cached = loadCachedResult(url, mode);
            if (cached) {
                renderAnalysisResult(cached, mode);
                showToast('Loaded cached result for this mode');
                autoModeSwitchInFlight = false;
                return;
            }

            if (
                useCache &&
                useCache.checked &&
                !autoModeSwitchInFlight &&
                hasAnyCachedResult(url)
            ) {
                autoModeSwitchInFlight = true;
                showToast(`Generating ${labelStr} from cached transcript...`);
                analyzeForm.requestSubmit();
            }
        });
    });

    // --- TABS LOGIC ---
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => {
                c.classList.remove('active');
                c.classList.add('hidden');
            });
            
            btn.classList.add('active');
            const target = btn.getAttribute('data-target');
            const targetEl = document.getElementById(target);
            if (targetEl) {
                targetEl.classList.remove('hidden');
                targetEl.classList.add('active');
            }
        });
    });

    // --- CHAT LOGIC ---
    const addChatMessage = (text, isUser = false) => {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${isUser ? 'user-message' : 'assistant-message'}`;
        
        const avatar = document.createElement('div');
        avatar.className = 'avatar';
        avatar.innerHTML = isUser ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-robot"></i>';
        
        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        
        // Parse markdown if assistant
        if (!isUser && typeof marked !== 'undefined') {
            bubble.innerHTML = marked.parse(text);
        } else {
            bubble.textContent = text;
        }

        msgDiv.appendChild(avatar);
        msgDiv.appendChild(bubble);
        chatMessages.appendChild(msgDiv);
        
        // auto scroll
        chatMessages.scrollTop = chatMessages.scrollHeight;
    };

    const addTypingIndicator = () => {
        const typingId = 'typing-' + Date.now();
        const msgDiv = document.createElement('div');
        msgDiv.className = `message assistant-message`;
        msgDiv.id = typingId;
        
        const avatar = document.createElement('div');
        avatar.className = 'avatar';
        avatar.innerHTML = '<i class="fa-solid fa-robot"></i>';
        
        const bubble = document.createElement('div');
        bubble.className = 'bubble chat-typing';
        bubble.innerHTML = '<span></span><span></span><span></span>';

        msgDiv.appendChild(avatar);
        msgDiv.appendChild(bubble);
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        return typingId;
    };

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = chatInput.value.trim();
        if (!query) return;

        chatInput.value = '';
        addChatMessage(query, true);
        
        const typingId = addTypingIndicator();

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    query: query, 
                    limit: 10,
                    provider: providerSelect ? providerSelect.value : null,
                    model_name: modelSelect ? modelSelect.value : null,
                    language: languageSelect ? languageSelect.value : 'Auto'
                })
            });

            const result = await response.json();
            
            // Remove typing indicator
            document.getElementById(typingId)?.remove();

            if (!response.ok) {
                throw new Error(result.detail || 'Chat failed');
            }

            addChatMessage(result.answer, false);
        } catch (error) {
            console.error(error);
            document.getElementById(typingId)?.remove();
            addChatMessage("Sorry, I encountered an error answering that.", false);
        }
    });

    // --- SETTINGS MODAL LOGIC ---
    const openSettingsBtn = document.getElementById('openSettingsBtn');
    const closeSettingsBtn = document.getElementById('closeSettingsBtn');
    const settingsModal = document.getElementById('settingsModal');
    const saveKeysBtn = document.getElementById('saveKeysBtn');
    
    if (openSettingsBtn && settingsModal) {
        openSettingsBtn.addEventListener('click', async () => {
            settingsModal.classList.remove('hidden');
            // Load current keys
            try {
                const res = await fetch('/api/settings/keys');
                const result = await res.json();
                if (result.status === 'success' && result.data) {
                    const keys = result.data;
                    document.getElementById('keyOpenAI').value = keys.openai || '';
                    document.getElementById('keyAnthropic').value = keys.anthropic || '';
                    document.getElementById('keyGroq').value = keys.groq || '';
                    document.getElementById('keyGrok').value = keys.grok || '';
                    document.getElementById('keyYouTube').value = keys.youtube || '';
                }
            } catch (e) {
                console.error('Failed to load keys', e);
            }
        });

        const closeModal = () => settingsModal.classList.add('hidden');
        closeSettingsBtn.addEventListener('click', closeModal);
        settingsModal.addEventListener('click', (e) => {
            if (e.target === settingsModal) closeModal();
        });

        saveKeysBtn.addEventListener('click', async () => {
            const payload = {};
            const keysMap = {
                'keyOpenAI': 'openai',
                'keyAnthropic': 'anthropic',
                'keyGroq': 'groq',
                'keyGrok': 'grok',
                'keyYouTube': 'youtube'
            };
            
            for (const [id, keyName] of Object.entries(keysMap)) {
                const el = document.getElementById(id);
                if (el && el.value.trim() !== '') {
                    payload[keyName] = el.value.trim();
                } else if (el) {
                    payload[keyName] = ''; // clear if empty
                }
            }
            
            const originalBtnHtml = saveKeysBtn.innerHTML;
            saveKeysBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
            saveKeysBtn.disabled = true;

            try {
                const res = await fetch('/api/settings/keys', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                if (res.ok) {
                    showToast('API Keys saved successfully!');
                    closeModal();
                    // Reload models list since keys update what providers are available
                    setTimeout(() => loadModels(), 500); 
                } else {
                    showToast('Error saving keys');
                }
            } catch (e) {
                console.error(e);
                showToast('Failed to save API keys');
            } finally {
                saveKeysBtn.innerHTML = originalBtnHtml;
                saveKeysBtn.disabled = false;
            }
        });
    }
});
