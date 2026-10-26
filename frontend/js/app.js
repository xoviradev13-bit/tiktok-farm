// State
let currentTab = 'tab-auto-pipeline';
let cachedGpmProfiles = [];
let cachedVideos = [];
let cachedCampaigns = [];
let activeStudioVideo = null;
let currentStudioFilter = 'all';

// DOM Ready
document.addEventListener('DOMContentLoaded', () => {
    applyCachedSchedulerState();
    setupNavigation();
    loadDashboardStats();
    loadGpmProfiles();
    loadVideos();
    loadSavedChannels();
    loadCampaigns();
    loadPipelineStatus();
    loadSchedulerSettings();
    loadTelegramChannels();
    loadFollowerSchedulerBadge();
    checkScanProgress();
    loadSystemTraySettings();
    applyColumnVisibility();
    startTopbarClock();

    // Close column dropdown & action menus when clicking outside
    document.addEventListener('click', (e) => {
        const container = document.querySelector('.col-picker-container');
        if (container && !container.contains(e.target)) {
            closeColumnDropdown();
        }
        if (!e.target.closest('.action-dropdown-wrap')) {
            closeAllActionMenus();
        }
    });

    // Close detail modal when clicking outside modal-content
    const detailModal = document.getElementById('channelDetailModal');
    if (detailModal) {
        detailModal.addEventListener('click', (e) => {
            if (e.target === detailModal) {
                closeChannelDetailModal();
            }
        });
    }

    const campaignModal = document.getElementById('newCampaignModal');
    if (campaignModal) {
        campaignModal.addEventListener('click', (e) => {
            if (e.target === campaignModal) {
                closeNewCampaignModal();
            }
        });
    }

    const editCampModal = document.getElementById('editCampaignModal');
    if (editCampModal) {
        editCampModal.addEventListener('click', (e) => {
            if (e.target === editCampModal) {
                closeEditCampaignModal();
            }
        });
    }

    const campLogsModal = document.getElementById('campaignLogsModal');
    if (campLogsModal) {
        campLogsModal.addEventListener('click', (e) => {
            if (e.target === campLogsModal) {
                closeCampaignLogsModal();
            }
        });
    }

    const schedModal = document.getElementById('schedulerSettingsModal');
    if (schedModal) {
        schedModal.addEventListener('click', (e) => {
            if (e.target === schedModal) {
                closeSchedulerSettingsModal();
            }
        });
    }

    const follSchedModal = document.getElementById('followerSchedulerModal');
    if (follSchedModal) {
        follSchedModal.addEventListener('click', (e) => {
            if (e.target === follSchedModal) {
                closeFollowerSchedulerModal();
            }
        });
    }

    const editUserModal = document.getElementById('editProfileUsernameModal');
    if (editUserModal) {
        editUserModal.addEventListener('click', (e) => {
            if (e.target === editUserModal) {
                closeEditUsernameModal();
            }
        });
    }

    // Keyboard ESC listener for modals
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeAllActionMenus();
            closeChannelDetailModal();
            closeNewCampaignModal();
            closeEditCampaignModal();
            closeCampaignLogsModal();
            closeSchedulerSettingsModal();
            closeFollowerSchedulerModal();
            closeEditUsernameModal();
        }
    });

    const btnSaveDetail = document.getElementById('btnToggleSaveFromDetail');
    if (btnSaveDetail) {
        btnSaveDetail.addEventListener('click', toggleSaveFromDetailModal);
    }

    // Auto refresh logs & stats every 8 seconds
    setInterval(loadDashboardStats, 8000);
});

// HTML Escaper for safe rendering
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Enhanced Toast notification helper supporting types ('error', 'warning', 'success', 'info') and structured error formatting
let toastDismissTimer = null;
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    if (!toast) return;

    // Backward compatibility: boolean isError
    let normalizedType = 'info';
    if (type === true || type === 'error' || type === 'danger') {
        normalizedType = 'error';
    } else if (type === 'warning' || type === 'warn') {
        normalizedType = 'warning';
    } else if (type === false || type === 'success') {
        normalizedType = 'success';
    } else if (typeof type === 'string' && ['info', 'error', 'warning', 'success'].includes(type.toLowerCase())) {
        normalizedType = type.toLowerCase();
    }

    // Format message if it's an object or array (e.g., FastAPI 422 detail)
    let displayMsg = '';
    if (typeof message === 'string') {
        displayMsg = message;
    } else if (Array.isArray(message)) {
        displayMsg = message.map(item => {
            if (typeof item === 'string') return item;
            if (item && item.msg) return item.msg;
            if (item && item.message) return item.message;
            return JSON.stringify(item);
        }).join('\n');
    } else if (message && typeof message === 'object') {
        if (message.detail) {
            displayMsg = typeof message.detail === 'string'
                ? message.detail
                : (Array.isArray(message.detail) ? message.detail.map(d => d.msg || JSON.stringify(d)).join('\n') : JSON.stringify(message.detail));
        } else if (message.message) {
            displayMsg = message.message;
        } else if (message.msg) {
            displayMsg = message.msg;
        } else {
            try {
                displayMsg = JSON.stringify(message);
            } catch (_) {
                displayMsg = String(message);
            }
        }
    } else {
        displayMsg = String(message || '');
    }

    // Icons per type
    let iconHtml = '<i class="fa-solid fa-circle-info toast-icon"></i>';
    if (normalizedType === 'error') {
        iconHtml = '<i class="fa-solid fa-circle-exclamation toast-icon"></i>';
    } else if (normalizedType === 'warning') {
        iconHtml = '<i class="fa-solid fa-triangle-exclamation toast-icon"></i>';
    } else if (normalizedType === 'success') {
        iconHtml = '<i class="fa-solid fa-circle-check toast-icon"></i>';
    }

    toast.className = `toast toast-${normalizedType}`;
    toast.innerHTML = `${iconHtml}<div class="toast-content">${escapeHtml(displayMsg).replace(/\n/g, '<br>')}</div>`;
    toast.classList.add('show');

    if (toastDismissTimer) clearTimeout(toastDismissTimer);
    toastDismissTimer = setTimeout(() => {
        toast.classList.remove('show');
    }, 4000);
}

// Input Error Feedback Helpers
function markInputError(elOrId, message = '', type = 'error') {
    const el = typeof elOrId === 'string' ? document.getElementById(elOrId) : elOrId;
    if (!el) {
        if (message) showToast(message, type);
        return;
    }

    el.classList.add('input-invalid');
    el.classList.remove('input-shake');
    // Force DOM reflow to re-trigger CSS shake animation
    void el.offsetWidth;
    el.classList.add('input-shake');

    setTimeout(() => {
        el.classList.remove('input-shake');
    }, 400);

    try {
        if (typeof el.focus === 'function') el.focus();
    } catch (_) {}

    // Add inline error feedback under input if message is supplied
    if (message && el.parentElement) {
        let errorMsgEl = el.parentElement.querySelector(`.input-error-msg[data-for="${el.id || ''}"]`);
        if (!errorMsgEl) {
            errorMsgEl = document.createElement('div');
            errorMsgEl.className = 'input-error-msg';
            if (el.id) errorMsgEl.setAttribute('data-for', el.id);
            if (el.nextSibling) {
                el.parentElement.insertBefore(errorMsgEl, el.nextSibling);
            } else {
                el.parentElement.appendChild(errorMsgEl);
            }
        }
        errorMsgEl.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> <span>${escapeHtml(message)}</span>`;
    }

    // Auto-remove error state when user changes or types in the field
    const clearHandler = () => {
        clearInputError(el);
        el.removeEventListener('input', clearHandler);
        el.removeEventListener('change', clearHandler);
    };
    el.addEventListener('input', clearHandler);
    el.addEventListener('change', clearHandler);

    if (message) {
        showToast(message, type);
    }
}

function clearInputError(elOrId) {
    const el = typeof elOrId === 'string' ? document.getElementById(elOrId) : elOrId;
    if (!el) return;

    el.classList.remove('input-invalid');
    el.classList.remove('input-shake');

    if (el.parentElement) {
        const errorMsgEl = el.parentElement.querySelector(`.input-error-msg[data-for="${el.id || ''}"]`);
        if (errorMsgEl) errorMsgEl.remove();
    }
}

function clearAllInputErrors(containerOrSelector) {
    const root = typeof containerOrSelector === 'string'
        ? document.querySelector(containerOrSelector)
        : (containerOrSelector || document);
    if (!root) return;
    root.querySelectorAll('.input-invalid').forEach(el => clearInputError(el));
    root.querySelectorAll('.input-error-msg').forEach(el => el.remove());
}

// Input Format Validators
function isValidYouTubeUrl(url) {
    if (!url || typeof url !== 'string') return false;
    const clean = url.trim();
    if (!clean) return false;
    // Check 11-char raw ID
    if (/^[a-zA-Z0-9_-]{11}$/.test(clean)) return true;
    // Check standard or shorts URL
    const ytRegex = /^(https?:\/\/)?(www\.|m\.)?(youtube\.com\/(watch\?v=|shorts\/|embed\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
    return ytRegex.test(clean);
}

function isValidTimeHHMM(timeStr) {
    if (!timeStr || typeof timeStr !== 'string') return false;
    return /^([01]?[0-9]|2[0-3]):[0-5][0-9]$/.test(timeStr.trim());
}

function isValidFolderName(name) {
    if (!name || typeof name !== 'string') return false;
    const clean = name.trim();
    if (!clean) return false;
    // Check forbidden Windows file/folder characters: \ / : * ? " < > |
    return !/[\\/:*?"<>|]/.test(clean);
}

function isValidProxyFormat(proxyStr) {
    if (!proxyStr || typeof proxyStr !== 'string') return true; // Optional proxy can be empty
    const clean = proxyStr.trim();
    if (!clean) return true;
    // Format: host:port, host:port:user:pass, user:pass@host:port (with optional scheme)
    return /^(https?:\/\/|socks5:\/\/)?([a-zA-Z0-9.-]+):(\d{2,5})(:[^:]+:[^:]+)?$/.test(clean) ||
           /^(https?:\/\/|socks5:\/\/)?([^:]+:[^@]+@)?([a-zA-Z0-9.-]+):(\d{2,5})$/.test(clean);
}


// Global Custom Confirmation Modal Dialog (replaces window.confirm to avoid "127.0.0.1:8088 says" address)
function showConfirmDialog({
    title = 'Xác Nhận Hành Động',
    message = 'Bạn có chắc chắn muốn thực hiện thao tác này?',
    details = '',
    confirmText = 'Xác Nhận',
    cancelText = 'Hủy Bỏ',
    confirmClass = 'btn-danger',
    icon = 'fa-solid fa-triangle-exclamation text-danger'
} = {}) {
    return new Promise((resolve) => {
        const modal = document.getElementById('modalGlobalConfirm');
        if (!modal) {
            resolve(window.confirm(message));
            return;
        }

        const titleEl = document.getElementById('globalConfirmTitle');
        const msgEl = document.getElementById('globalConfirmMessage');
        const detEl = document.getElementById('globalConfirmDetails');
        const iconEl = document.getElementById('globalConfirmIcon');
        const btnOk = document.getElementById('btnGlobalConfirmOk');
        const btnCancel = document.getElementById('btnGlobalConfirmCancel');
        const btnClose = document.getElementById('btnGlobalConfirmClose');

        if (titleEl) titleEl.textContent = title;
        if (msgEl) {
            msgEl.textContent = message;
            msgEl.style.wordBreak = 'break-word';
            msgEl.style.overflowWrap = 'anywhere';
        }
        if (detEl) {
            detEl.textContent = details || '';
            detEl.style.display = details ? 'block' : 'none';
            detEl.style.wordBreak = 'break-word';
            detEl.style.overflowWrap = 'anywhere';
        }
        if (iconEl) iconEl.className = icon;
        if (btnOk) {
            btnOk.className = `btn ${confirmClass}`;
            btnOk.innerHTML = `<i class="fa-solid fa-check"></i> ${confirmText}`;
        }
        if (btnCancel) btnCancel.textContent = cancelText;

        let resolved = false;
        const cleanup = (result) => {
            if (resolved) return;
            resolved = true;
            modal.classList.remove('active');
            btnOk?.removeEventListener('click', onOk);
            btnCancel?.removeEventListener('click', onCancel);
            btnClose?.removeEventListener('click', onCancel);
            modal.removeEventListener('click', onBackdrop);
            document.removeEventListener('keydown', onKeyDown);
            resolve(result);
        };

        const onOk = () => cleanup(true);
        const onCancel = () => cleanup(false);
        const onBackdrop = (e) => { if (e.target === modal) cleanup(false); };
        const onKeyDown = (e) => { if (e.key === 'Escape') cleanup(false); };

        btnOk?.addEventListener('click', onOk);
        btnCancel?.addEventListener('click', onCancel);
        btnClose?.addEventListener('click', onCancel);
        modal.addEventListener('click', onBackdrop);
        document.addEventListener('keydown', onKeyDown);

        modal.classList.add('active');
    });
}

// Sidebar Toggle
function toggleSidebar() {
    const collapsed = document.body.classList.toggle('sidebar-collapsed');
    const btn = document.getElementById('sidebarToggleBtn');
    if (btn) {
        btn.setAttribute('data-tooltip', collapsed ? 'Mở rộng' : 'Thu gọn');
    }
}

// Navigation Tabs
function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tabId = item.getAttribute('data-tab');
            switchTab(tabId);
        });
    });
    // Đồng bộ ngay tiêu đề topbar và nội dung tab đang mở
    switchTab(currentTab);
}

function switchTab(tabId) {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
        document.activeElement.blur();
    }
    // Aliases support
    if (tabId === 'tab-youtube') {
        tabId = 'tab-sources';
        switchSourceSubTab('search');
    } else if (tabId === 'tab-saved-channels') {
        tabId = 'tab-sources';
        switchSourceSubTab('saved');
    } else if (tabId === 'tab-pipeline') {
        tabId = 'tab-auto-pipeline';
    } else if (tabId === 'tab-ai-editor') {
        tabId = 'tab-video-studio';
    }

    currentTab = tabId;

    // Update active nav item
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    const activeNav = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
    if (activeNav) activeNav.classList.add('active');

    // Update active tab pane
    document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
    const activePane = document.getElementById(tabId);
    if (activePane) activePane.classList.add('active');

    // Update Stepper Banner Highlight
    document.querySelectorAll('.step-item').forEach(el => el.classList.remove('active'));
    if (tabId === 'tab-sources') {
        document.getElementById('step1Indicator')?.classList.add('active');
    } else if (tabId === 'tab-video-studio') {
        document.getElementById('step2Indicator')?.classList.add('active');
    } else if (tabId === 'tab-auto-pipeline') {
        document.getElementById('step3Indicator')?.classList.add('active');
    } else if (tabId === 'tab-gpm-farm' || tabId === 'tab-tracker') {
        document.getElementById('step4Indicator')?.classList.add('active');
    }

    // Update Topbar Title & Subtitle for every sidebar item
    const tabMeta = {
        'tab-auto-pipeline': {
            title: 'Chiến Dịch Tự Động Hóa (Auto-Pilot)',
            sub: 'Quy trình khép kín: Quét RSS Kênh → Tải MP4 → AI Render 9:16 → Tự Đăng TikTok GPM'
        },
        'tab-video-studio': {
            title: 'Studio Biên Tập Video 9:16',
            sub: 'Tùy chỉnh mẫu cắt >60s chuẩn Quỹ Beta & xem trước trực tiếp trên điện thoại mô phỏng'
        },
        'tab-sources': {
            title: 'Quản Lý Kênh YouTube Nguồn',
            sub: 'Theo dõi nguồn RSS chất lượng cao và quét từ khóa tự động tìm kênh mới'
        },
        'tab-gpm-farm': {
            title: 'Dàn Tài Khoản GPMLogin',
            sub: 'Quản lý profile TikTok, theo dõi tăng trưởng follower và cấu hình thông báo Telegram'
        },
        'tab-overview': {
            title: 'Bảng Điều Khiển Tổng Quan',
            sub: 'Số liệu tổng quan hệ thống, tài nguyên và tiến độ tăng trưởng'
        },
        'tab-pipeline-queue': {
            title: 'Hàng Đợi & Lịch Đăng (Kanban)',
            sub: 'Theo dõi 4 giai đoạn: Mới tải về → Đã render 9:16 → Chờ lịch đăng → Đã đăng'
        },
        'tab-logs': {
            title: 'Nhật Ký Hệ Thống',
            sub: 'Theo dõi toàn bộ sự kiện, tiến trình chạy nền và cảnh báo lỗi thời gian thực'
        },
        'tab-ai-usage': {
            title: 'Quản Lý Mức Sử Dụng & Chi Phí AI',
            sub: 'Theo dõi lượng token, số lượt gọi API và ngân sách hệ thống theo thời gian thực.'
        },
        'tab-audio-studio': {
            title: 'Kho Âm Thanh & Nhạc Nền (Audio Studio)',
            sub: 'Tìm kiếm nhạc YouTube No-Copyright, tải lên MP3 và quản lý playlist chủ đề theo kênh'
        },
        'tab-settings': {
            title: 'Cài Đặt API & Cấu Hình Hệ Thống',
            sub: 'Thiết lập YouTube Data API, OpenAI, Gemini và Telegram Alert Bot'
        }
    };
    const meta = tabMeta[tabId] || { title: 'TikTok Beta Farm', sub: 'Hệ thống tự động hóa khai thác YouTube sang TikTok Beta' };
    const titleEl = document.getElementById('pageTitle');
    const subEl = document.getElementById('pageSubtitle');
    if (titleEl) titleEl.textContent = meta.title;
    if (subEl) subEl.textContent = meta.sub;

    if (tabId === 'tab-auto-pipeline') {
        loadCampaigns();
        loadPipelineStatus();
    } else if (tabId === 'tab-video-studio') {
        loadStudioVideos();
    } else if (tabId === 'tab-sources') {
        loadSavedChannels();
    } else if (tabId === 'tab-audio-studio') {
        loadAudioCategories();
    } else if (tabId === 'tab-gpm-farm' || tabId === 'tab-tracker') {
        loadGpmProfiles();
        checkScanProgress();
    } else if (tabId === 'tab-pipeline-queue') {
        loadPipelineStatus();
    } else if (tabId === 'tab-ai-usage') {
        loadAiUsageStats();
    } else if (tabId === 'tab-settings') {
        loadApiKeySettings();
        loadSchedulerSettings();
    } else if (tabId === 'tab-logs') {
        loadFileLogs();
    }
}

// Subnav switcher for Sources
function switchSourceSubTab(sub) {
    const btnSaved = document.getElementById('btnSubnavSaved');
    const btnSearch = document.getElementById('btnSubnavSearch');
    const viewSaved = document.getElementById('sourceSubViewSaved');
    const viewSearch = document.getElementById('sourceSubViewSearch');

    if (sub === 'saved') {
        btnSaved?.classList.add('active');
        btnSearch?.classList.remove('active');
        if (viewSaved) viewSaved.style.display = 'block';
        if (viewSearch) viewSearch.style.display = 'none';
        loadSavedChannels();
    } else {
        btnSearch?.classList.add('active');
        btnSaved?.classList.remove('active');
        if (viewSaved) viewSaved.style.display = 'none';
        if (viewSearch) viewSearch.style.display = 'block';
    }
}

// Live ticking clock in sticky topbar
function startTopbarClock() {
    function update() {
        const el = document.getElementById('topbarClock');
        if (!el) return;
        const now = new Date();
        const timeStr = now.toLocaleTimeString('vi-VN', { hour12: false });
        el.textContent = timeStr;
    }
    update();
    setInterval(update, 1000);
}

// 1. Dashboard Stats
async function loadDashboardStats() {
    try {
        const res = await fetch('/api/dashboard/stats');
        const data = await res.json();

        document.getElementById('statChannels').textContent = data.total_channels;
        document.getElementById('statVideos').textContent = data.total_videos;
        document.getElementById('statProfiles').textContent = data.total_profiles;
        document.getElementById('stat10k').textContent = data.eligible_10k_count;

        // Stepper stats sync
        const sSource = document.getElementById('stepperSourceStats');
        if (sSource) sSource.textContent = `${data.total_channels} kênh theo dõi`;

        const sGpm = document.getElementById('stepperGpmStats');
        if (sGpm) sGpm.textContent = `${data.total_profiles} nick GPM (${data.eligible_10k_count} đạt 10K)`;

        const sSourceBadge = document.getElementById('sourceSavedCountBadge');
        if (sSourceBadge) sSourceBadge.textContent = data.total_channels;

        // Update GPM status
        const gpmStatusText = document.getElementById('gpmStatusText');
        const chkGpm = document.getElementById('chkGpm');
        if (data.gpm_health && data.gpm_health.running) {
            gpmStatusText.textContent = `Online (${data.gpm_health.profile_count} Profiles)`;
            gpmStatusText.style.color = '#10b981';
            if (chkGpm) {
                chkGpm.className = 'badge badge-success';
                chkGpm.textContent = 'Kết Nối Tốt';
            }
        } else {
            gpmStatusText.textContent = 'Offline (Cổng :19995)';
            gpmStatusText.style.color = '#ef4444';
            if (chkGpm) {
                chkGpm.className = 'badge badge-danger';
                chkGpm.textContent = 'Chưa Mở GPM';
            }
        }

        // Update logs
        const logTerminal = document.getElementById('logTerminal');
        if (data.recent_logs && data.recent_logs.length > 0) {
            logTerminal.innerHTML = data.recent_logs.map(log => {
                const cls = log.level === 'ERROR' ? 'error' : (log.level === 'WARNING' ? 'warning' : 'info');
                return `<div class="log-line ${cls}">[${log.created_at || 'LOG'}] [${log.level}] ${escapeHtml(log.message)}</div>`;
            }).join('');
        }

        // Update Active Issues button in Topbar
        const btnIssues = document.getElementById('btnSystemIssues');
        const badgeText = document.getElementById('issueBadgeText');
        if (btnIssues && badgeText) {
            const count = data.active_issues_count || 0;
            if (count > 0) {
                btnIssues.style.display = 'inline-flex';
                badgeText.textContent = `${count} Cảnh Báo`;
                if (data.has_critical_issues) {
                    btnIssues.className = 'btn btn-danger btn-sm has-tooltip tooltip-left';
                } else {
                    btnIssues.className = 'btn btn-warning btn-sm has-tooltip tooltip-left';
                }
            } else {
                btnIssues.style.display = 'none';
            }
        }
    } catch (err) {
        console.error('Error fetching stats:', err);
    }
}

// 2. YouTube Search & Table State
let rawYtChannels = [];
let currentSortField = 'default';
let currentSortDirection = 'asc';
let filterActiveOnly = false;
let filterSaved = 'all'; // 'all', 'saved', 'unsaved'
let filterCountry = 'all';
let filterMinViews = 0;
let filterMinSubs = 0;
let filterCadence = 'all'; // 'all', 'daily', 'frequent', 'weekly', 'custom'
let filterKeyword = '';
let filterCustomViews = null;
let filterCustomSubs = null;
let filterCustomCadence = null;

// ======================== Column Picker Management ========================
function toggleColumnDropdown(e) {
    if (e) e.stopPropagation();
    const dropdown = document.getElementById('colPickerDropdown');
    if (!dropdown) return;
    dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
}

function closeColumnDropdown() {
    const dropdown = document.getElementById('colPickerDropdown');
    if (dropdown) dropdown.style.display = 'none';
}

function getHiddenColumns() {
    try {
        const saved = localStorage.getItem('yt_hidden_cols');
        return saved ? JSON.parse(saved) : [];
    } catch {
        return [];
    }
}

function setHiddenColumns(cols) {
    try {
        localStorage.setItem('yt_hidden_cols', JSON.stringify(cols));
    } catch (e) { }
}

function toggleColVisibility(colKey, isVisible) {
    let hiddenCols = getHiddenColumns();
    if (!isVisible) {
        if (!hiddenCols.includes(colKey)) hiddenCols.push(colKey);
    } else {
        hiddenCols = hiddenCols.filter(k => k !== colKey);
    }
    setHiddenColumns(hiddenCols);
    applyColumnVisibility();
}

function applyColumnVisibility() {
    const hiddenCols = getHiddenColumns();
    document.querySelectorAll('[data-col]').forEach(el => {
        const colKey = el.getAttribute('data-col');
        if (hiddenCols.includes(colKey)) {
            el.classList.add('col-hidden');
        } else {
            el.classList.remove('col-hidden');
        }
    });

    document.querySelectorAll('#colPickerDropdown input[data-col-target]').forEach(chk => {
        const colKey = chk.getAttribute('data-col-target');
        chk.checked = !hiddenCols.includes(colKey);
    });
}

function getCountryBadge(code) {
    if (!code || code === 'N/A' || code === 'ZZ' || code === 'None') {
        return '<span class="badge-country text-muted"><i class="fa-solid fa-globe"></i> N/A</span>';
    }
    const c = code.trim().toUpperCase();
    const flags = {
        'US': '🇺🇸 US', 'VN': '🇻🇳 VN', 'GB': '🇬🇧 GB', 'UK': '🇬🇧 UK',
        'CA': '🇨🇦 CA', 'AU': '🇦🇺 AU', 'DE': '🇩🇪 DE', 'FR': '🇫🇷 FR',
        'JP': '🇯🇵 JP', 'KR': '🇰🇷 KR', 'IN': '🇮🇳 IN', 'BR': '🇧🇷 BR',
        'RU': '🇷🇺 RU', 'ES': '🇪🇸 ES', 'IT': '🇮🇹 IT', 'ID': '🇮🇩 ID',
        'PH': '🇵🇭 PH', 'TH': '🇹🇭 TH', 'SG': '🇸🇬 SG', 'MX': '🇲🇽 MX',
        'NL': '🇳🇱 NL', 'SE': '🇸🇪 SE', 'NO': '🇳🇴 NO', 'CH': '🇨🇭 CH',
    };
    const label = flags[c] || `🌐 ${c}`;
    return `<span class="badge-country" title="Quốc gia: ${escapeHtml(c)}">${label}</span>`;
}

function copyTextToClipboard(text, msg = 'Đã sao chép vào bộ nhớ tạm!') {
    if (!text) return;
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(() => {
            showToast(msg);
        }).catch(() => {
            _fallbackCopy(text, msg);
        });
    } else {
        _fallbackCopy(text, msg);
    }
}

function _fallbackCopy(text, msg) {
    const input = document.createElement('textarea');
    input.value = text;
    input.style.position = 'fixed';
    input.style.opacity = '0';
    document.body.appendChild(input);
    input.select();
    try {
        document.execCommand('copy');
        showToast(msg);
    } catch (e) {
        showToast('Không thể sao chép: ' + e.message, true);
    }
    document.body.removeChild(input);
}

// ==================== CSV Export Helper ====================
function downloadCsv(filename, rows) {
    if (!rows || !rows.length) {
        showToast('Không có dữ liệu để xuất file CSV!', true);
        return;
    }
    const csvContent = '\uFEFF' + rows.map(row =>
        row.map(cell => {
            if (cell === null || cell === undefined) return '""';
            let str = String(cell).replace(/"/g, '""');
            return `"${str}"`;
        }).join(',')
    ).join('\r\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.setAttribute('download', filename);
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(`Đã xuất thành công ${rows.length - 1} dòng ra file "${filename}"!`);
}

function populateCountryFilterOptions(channels) {
    const sel = document.getElementById('ytFilterCountrySelect');
    if (!sel) return;
    const currentVal = filterCountry;

    const counts = {};
    channels.forEach(c => {
        const country = (c.country || 'N/A').toUpperCase();
        counts[country] = (counts[country] || 0) + 1;
    });

    const sortedCountries = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);

    let options = '<option value="all">Tất cả quốc gia</option>';
    sortedCountries.forEach(code => {
        const flagMap = { 'US': '🇺🇸', 'VN': '🇻🇳', 'GB': '🇬🇧', 'CA': '🇨🇦', 'AU': '🇦🇺', 'DE': '🇩🇪', 'FR': '🇫🇷', 'JP': '🇯🇵', 'KR': '🇰🇷', 'IN': '🇮🇳' };
        const flag = flagMap[code] || '🌐';
        options += `<option value="${code}">${flag} ${code} (${counts[code]} kênh)</option>`;
    });

    sel.innerHTML = options;
    if (counts[currentVal]) {
        sel.value = currentVal;
    } else {
        filterCountry = 'all';
        sel.value = 'all';
    }
}

async function searchYouTubeChannels() {
    const kwEl = document.getElementById('ytSearchKeyword');
    const maxResultsEl = document.getElementById('ytMaxResults');
    const keyword = kwEl ? kwEl.value.trim() : '';
    const maxResults = maxResultsEl ? parseInt(maxResultsEl.value, 10) : 50;
    const tbody = document.getElementById('ytChannelsBody');
    const toolbar = document.getElementById('ytTableToolbar');
    const btn = document.getElementById('btnSearchYt');

    if (!keyword) {
        markInputError('ytSearchKeyword', 'Vui lòng nhập từ khóa ngách YouTube!');
        return;
    }
    if (isNaN(maxResults) || maxResults < 1 || maxResults > 50) {
        markInputError('ytMaxResults', 'Số lượng kênh quét phải từ 1 đến 50!');
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="margin-right: 8px;"></i> Đang Quét...';
    }

    tbody.innerHTML = `
        <tr>
            <td colspan="12" class="text-center py-4">
                <i class="fa-solid fa-spinner fa-spin" style="margin-right: 8px;"></i> Đang quét và phân tích tần suất đăng bài của các kênh YouTube...
            </td>
        </tr>
    `;

    try {
        const res = await fetch('/api/youtube/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyword, max_results: maxResults })
        });
        const data = await res.json();

        if (!res.ok) {
            showToast(data.detail || data.message || 'Lỗi khi quét kênh YouTube', 'error');
            tbody.innerHTML = `<tr><td colspan="12" class="text-center py-4 text-danger">${escapeHtml(data.detail || data.message || 'Lỗi quét kênh')}</td></tr>`;
            return;
        }

        if (!data.channels || data.channels.length === 0) {
            rawYtChannels = [];
            tbody.innerHTML = `<tr><td colspan="12" class="text-center py-4 text-muted">Không tìm thấy kênh nào với từ khóa này.</td></tr>`;
            return;
        }

        rawYtChannels = data.channels.map((ch, idx) => ({
            ...ch,
            originalIndex: idx,
            is_saved: Boolean(ch.is_saved)
        }));

        currentSortField = 'default';
        currentSortDirection = 'asc';
        filterActiveOnly = false;
        filterSaved = 'all';
        filterCountry = 'all';
        filterMinViews = 0;
        filterMinSubs = 0;
        filterCadence = 'all';
        filterKeyword = '';
        filterCustomViews = null;
        filterCustomSubs = null;
        filterCustomCadence = null;

        populateCountryFilterOptions(rawYtChannels);

        const sortSelect = document.getElementById('ytSortSelect');
        if (sortSelect) sortSelect.value = 'default';
        const filterSavedSel = document.getElementById('ytFilterSavedSelect');
        if (filterSavedSel) filterSavedSel.value = 'all';
        const filterCheck = document.getElementById('ytFilterActiveOnly');
        if (filterCheck) filterCheck.checked = false;
        const filterViewsSel = document.getElementById('ytFilterViewsSelect');
        if (filterViewsSel) filterViewsSel.value = '0';
        const filterSubsSel = document.getElementById('ytFilterSubsSelect');
        if (filterSubsSel) filterSubsSel.value = '0';
        const filterCadenceSel = document.getElementById('ytFilterCadenceSelect');
        if (filterCadenceSel) filterCadenceSel.value = 'all';
        const filterKwInput = document.getElementById('ytFilterKeyword');
        if (filterKwInput) filterKwInput.value = '';

        const customViewsInp = document.getElementById('ytCustomViewsInput');
        if (customViewsInp) { customViewsInp.value = ''; customViewsInp.style.display = 'none'; }
        const customSubsInp = document.getElementById('ytCustomSubsInput');
        if (customSubsInp) { customSubsInp.value = ''; customSubsInp.style.display = 'none'; }
        const customCadenceInp = document.getElementById('ytCustomCadenceInput');
        if (customCadenceInp) { customCadenceInp.value = ''; customCadenceInp.style.display = 'none'; }

        updateSortDirectionBtn();
        renderYtChannelsTable();
        showToast(`Đã tìm thấy ${data.channels.length} kênh theo từ khóa!`);
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="12" class="text-center py-4 text-danger">Lỗi khi quét kênh: ${err.message}</td></tr>`;
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-bolt" style="margin-right: 6px;"></i> Bắt Đầu Quét';
        }
    }
}

function handleFilterCountryChange(val) {
    filterCountry = val;
    renderYtChannelsTable();
}

function handleFilterViewsChange(val) {
    const customInp = document.getElementById('ytCustomViewsInput');
    if (val === 'custom') {
        if (customInp) {
            customInp.style.display = 'inline-block';
            customInp.focus();
            filterCustomViews = customInp.value ? (parseFloat(customInp.value) || 0) : null;
        }
        filterMinViews = filterCustomViews || 0;
    } else {
        if (customInp) customInp.style.display = 'none';
        filterCustomViews = null;
        filterMinViews = parseInt(val, 10) || 0;
    }
    renderYtChannelsTable();
}

function handleCustomViewsInput(val) {
    const num = parseFloat(val);
    filterCustomViews = !isNaN(num) && num > 0 ? num : null;
    filterMinViews = filterCustomViews || 0;
    renderYtChannelsTable();
}

function handleFilterSubsChange(val) {
    const customInp = document.getElementById('ytCustomSubsInput');
    if (val === 'custom') {
        if (customInp) {
            customInp.style.display = 'inline-block';
            customInp.focus();
            filterCustomSubs = customInp.value ? (parseFloat(customInp.value) || 0) : null;
        }
        filterMinSubs = filterCustomSubs || 0;
    } else {
        if (customInp) customInp.style.display = 'none';
        filterCustomSubs = null;
        filterMinSubs = parseInt(val, 10) || 0;
    }
    renderYtChannelsTable();
}

function handleCustomSubsInput(val) {
    const num = parseFloat(val);
    filterCustomSubs = !isNaN(num) && num > 0 ? num : null;
    filterMinSubs = filterCustomSubs || 0;
    renderYtChannelsTable();
}

function handleFilterCadenceChange(val) {
    const customInp = document.getElementById('ytCustomCadenceInput');
    if (val === 'custom') {
        if (customInp) {
            customInp.style.display = 'inline-block';
            customInp.focus();
            filterCustomCadence = customInp.value ? (parseFloat(customInp.value) || null) : null;
        }
        filterCadence = 'custom';
    } else {
        if (customInp) customInp.style.display = 'none';
        filterCustomCadence = null;
        filterCadence = val;
    }
    renderYtChannelsTable();
}

function handleCustomCadenceInput(val) {
    const num = parseFloat(val);
    filterCustomCadence = !isNaN(num) && num > 0 ? num : null;
    renderYtChannelsTable();
}

function resetYtFilters() {
    filterCountry = 'all';
    filterMinViews = 0;
    filterMinSubs = 0;
    filterCadence = 'all';
    filterActiveOnly = false;
    filterSaved = 'all';
    filterKeyword = '';
    filterCustomViews = null;
    filterCustomSubs = null;
    filterCustomCadence = null;
    currentSortField = 'default';
    currentSortDirection = 'asc';

    const elSort = document.getElementById('ytSortSelect');
    if (elSort) elSort.value = 'default';
    const elCountry = document.getElementById('ytFilterCountrySelect');
    if (elCountry) elCountry.value = 'all';
    const elViews = document.getElementById('ytFilterViewsSelect');
    if (elViews) elViews.value = '0';
    const elSubs = document.getElementById('ytFilterSubsSelect');
    if (elSubs) elSubs.value = '0';
    const elCadence = document.getElementById('ytFilterCadenceSelect');
    if (elCadence) elCadence.value = 'all';
    const elSaved = document.getElementById('ytFilterSavedSelect');
    if (elSaved) elSaved.value = 'all';
    const elActive = document.getElementById('ytFilterActiveOnly');
    if (elActive) elActive.checked = false;
    const elKw = document.getElementById('ytFilterKeyword');
    if (elKw) elKw.value = '';

    const customViewsInp = document.getElementById('ytCustomViewsInput');
    if (customViewsInp) { customViewsInp.value = ''; customViewsInp.style.display = 'none'; }
    const customSubsInp = document.getElementById('ytCustomSubsInput');
    if (customSubsInp) { customSubsInp.value = ''; customSubsInp.style.display = 'none'; }
    const customCadenceInp = document.getElementById('ytCustomCadenceInput');
    if (customCadenceInp) { customCadenceInp.value = ''; customCadenceInp.style.display = 'none'; }

    updateSortDirectionBtn();
    renderYtChannelsTable();
    showToast('Đã đặt lại toàn bộ bộ lọc!');
}

function getFilteredYtChannels() {
    let list = [...rawYtChannels];

    // 1. Lọc theo checkbox Đang hoạt động
    if (filterActiveOnly) {
        list = list.filter(c => c.is_active === 1);
    }

    // 2. Lọc theo trạng thái Đã lưu / Chưa lưu
    if (filterSaved === 'saved') {
        list = list.filter(c => c.is_saved);
    } else if (filterSaved === 'unsaved') {
        list = list.filter(c => !c.is_saved);
    }

    // 3. Lọc theo Quốc gia
    if (filterCountry !== 'all') {
        list = list.filter(c => (c.country || 'N/A').toUpperCase() === filterCountry.toUpperCase());
    }

    // 4. Lọc theo Views tối thiểu
    if (filterMinViews > 0) {
        list = list.filter(c => (c.avg_views || 0) >= filterMinViews);
    }

    // 5. Lọc theo Subs tối thiểu
    if (filterMinSubs > 0) {
        list = list.filter(c => (c.subscriber_count || 0) >= filterMinSubs);
    }

    // 6. Lọc theo Tần suất
    if (filterCadence === 'daily') {
        list = list.filter(c => c.upload_cadence_days > 0 && c.upload_cadence_days <= 1.0);
    } else if (filterCadence === 'frequent') {
        list = list.filter(c => c.upload_cadence_days > 0 && c.upload_cadence_days <= 3.0);
    } else if (filterCadence === 'weekly') {
        list = list.filter(c => c.upload_cadence_days > 0 && c.upload_cadence_days <= 7.0);
    } else if (filterCadence === 'custom' && filterCustomCadence !== null) {
        list = list.filter(c => c.upload_cadence_days > 0 && c.upload_cadence_days <= filterCustomCadence);
    }

    // 7. Lọc theo từ khóa tên kênh / ID / handle
    if (filterKeyword) {
        const kw = filterKeyword.toLowerCase().trim();
        list = list.filter(c =>
            (c.title || '').toLowerCase().includes(kw) ||
            (c.channel_id || '').toLowerCase().includes(kw) ||
            (c.handle || '').toLowerCase().includes(kw) ||
            (c.country || '').toLowerCase().includes(kw)
        );
    }

    // 8. Sắp xếp
    if (currentSortField !== 'default') {
        list.sort((a, b) => {
            let res = 0;
            if (currentSortField === 'title') {
                res = (a.title || '').localeCompare(b.title || '', 'vi', { sensitivity: 'base' });
            } else if (currentSortField === 'country') {
                res = (a.country || '').localeCompare(b.country || '');
            } else if (currentSortField === 'subscriber_count') {
                res = (a.subscriber_count || 0) - (b.subscriber_count || 0);
            } else if (currentSortField === 'video_count') {
                res = (a.video_count || 0) - (b.video_count || 0);
            } else if (currentSortField === 'avg_views') {
                res = (a.avg_views || 0) - (b.avg_views || 0);
            } else if (currentSortField === 'total_view_count') {
                res = (a.total_view_count || 0) - (b.total_view_count || 0);
            } else if (currentSortField === 'views_per_sub_ratio') {
                res = (a.views_per_sub_ratio || 0) - (b.views_per_sub_ratio || 0);
            } else if (currentSortField === 'days_since_last_upload') {
                const da = a.days_since_last_upload !== undefined && a.days_since_last_upload !== null ? a.days_since_last_upload : 9999;
                const db = b.days_since_last_upload !== undefined && b.days_since_last_upload !== null ? b.days_since_last_upload : 9999;
                res = da - db;
            } else if (currentSortField === 'upload_cadence_days') {
                const ca = a.upload_cadence_days > 0 ? a.upload_cadence_days : 9999;
                const cb = b.upload_cadence_days > 0 ? b.upload_cadence_days : 9999;
                res = ca - cb;
            } else if (currentSortField === 'is_active') {
                res = (a.is_active || 0) - (b.is_active || 0);
            } else if (currentSortField === 'is_saved') {
                res = (a.is_saved ? 1 : 0) - (b.is_saved ? 1 : 0);
            }
            return currentSortDirection === 'asc' ? res : -res;
        });
    }

    return list;
}

function exportYtSearchCsv() {
    let list = getFilteredYtChannels();
    if (!list || !list.length) {
        list = rawYtChannels || [];
    }
    if (!list.length) {
        showToast('Không có kênh nào trong danh sách quét để xuất CSV!', true);
        return;
    }

    const headers = [
        'Channel ID',
        'Tên Kênh',
        'Handle',
        'URL Kênh',
        'Quốc Gia',
        'Subscribers',
        'Tổng Số Video',
        'Lượt Xem TB',
        'Tổng Lượt Xem Kênh',
        'Viral Ratio',
        'Video Mới Nhất',
        'Số Ngày Kể Từ Video Cuối',
        'Tần Suất Đăng (Ngày/Vid)',
        'Mô Tả Tần Suất',
        'Trạng Thái Hoạt Động',
        'Đã Lưu Vào Hệ Thống'
    ];

    const rows = [headers];
    list.forEach(c => {
        rows.push([
            c.channel_id || '',
            c.title || '',
            c.handle || '',
            c.url || (c.channel_id ? `https://www.youtube.com/channel/${c.channel_id}` : ''),
            c.country || 'N/A',
            c.subscriber_count !== undefined && c.subscriber_count !== null ? c.subscriber_count : '',
            c.video_count !== undefined && c.video_count !== null ? c.video_count : '',
            c.avg_views !== undefined && c.avg_views !== null ? c.avg_views : '',
            c.total_view_count !== undefined && c.total_view_count !== null ? c.total_view_count : '',
            c.views_per_sub_ratio !== undefined && c.views_per_sub_ratio !== null ? Number(c.views_per_sub_ratio).toFixed(2) : '',
            c.last_upload_date || '',
            c.days_since_last_upload !== undefined && c.days_since_last_upload !== null ? c.days_since_last_upload : '',
            c.upload_cadence_days || '',
            c.cadence_description || '',
            c.is_active ? 'Đang hoạt động' : 'Ít đăng',
            c.is_saved ? 'Đã lưu' : 'Chưa lưu'
        ]);
    });

    const dateStr = new Date().toISOString().split('T')[0];
    downloadCsv(`kenh_youtube_tim_kiem_${dateStr}.csv`, rows);
}

function renderYtChannelsTable() {
    const tbody = document.getElementById('ytChannelsBody');
    const countBadge = document.getElementById('ytResultCountBadge');

    const list = getFilteredYtChannels();

    // Update result count badge
    if (countBadge) {
        countBadge.textContent = `${list.length}/${rawYtChannels.length} Kênh`;
    }

    // Update table header icons
    updateHeaderSortIcons();

    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="12" class="text-center py-4 text-muted">Không có kênh nào phù hợp với bộ lọc hiện tại.</td></tr>`;
        return;
    }

    tbody.innerHTML = list.map((c) => {
        const ratio = c.views_per_sub_ratio || 0;
        let ratioBadge = '';
        if (ratio > 0) {
            const ratioClass = ratio >= 2.0 ? 'high' : (ratio >= 0.5 ? 'good' : '');
            const fire = ratio >= 1.0 ? '🔥 ' : '';
            ratioBadge = `<div class="badge-ratio ${ratioClass}" title="Tỷ lệ lượt xem trên số người theo dõi">${fire}Ratio: ${ratio.toFixed(2)}x</div>`;
        }

        const handleText = c.handle ? `<span class="table-text-truncate" style="max-width:180px; font-size:11px; color:var(--accent-cyan); font-weight:500;" title="${escapeHtml(c.handle)}">${escapeHtml(c.handle)}</span>` : '';
        const cid = c.channel_id || '';
        const channelUrl = c.url || (cid ? `https://www.youtube.com/channel/${cid}` : '#');
        const thumbImg = c.thumbnail_url
            ? `<img src="${c.thumbnail_url}" alt="" class="channel-avatar-clickable" onclick="openChannelDetailModal(${c.originalIndex})" style="width:38px; height:38px; border-radius:50%; object-fit:cover; border:1px solid rgba(255,255,255,0.1); flex-shrink:0;" title="Bấm xem chi tiết kênh">`
            : `<div class="channel-avatar-clickable" onclick="openChannelDetailModal(${c.originalIndex})" style="width:38px; height:38px; border-radius:50%; background:rgba(255,255,255,0.06); display:flex; align-items:center; justify-content:center; color:var(--text-muted); flex-shrink:0;" title="Bấm xem chi tiết kênh"><i class="fa-brands fa-youtube"></i></div>`;

        return `
        <tr id="ch-row-${c.originalIndex}" class="${c.is_saved ? 'row-saved' : ''}">
            <td data-col="col-title">
                <div style="display:flex; align-items:flex-start; gap:10px;">
                    ${thumbImg}
                    <div style="display:flex; flex-direction:column; gap:2px; min-width:0;">
                        <strong class="channel-title-link" onclick="openChannelDetailModal(${c.originalIndex})" title="Bấm xem chi tiết kênh: ${escapeHtml(c.title)}">${escapeHtml(c.title)}</strong>
                        ${handleText}
                        <div style="margin-top:3px;">
                            <a href="${escapeHtml(channelUrl)}" target="_blank" rel="noopener" class="channel-link-tag" title="Mở trang YouTube của kênh này">
                                <i class="fa-solid fa-arrow-up-right-from-square"></i> Mở kênh
                            </a>
                        </div>
                    </div>
                </div>
            </td>
            <td data-col="col-id">
                <div style="display:flex; align-items:center; gap:4px;">
                    <span class="channel-id-tag" title="${escapeHtml(cid)}">${escapeHtml(cid)}</span>
                    <button type="button" class="btn-copy-id" onclick="copyTextToClipboard('${escapeHtml(cid)}', 'Đã sao chép Channel ID!')" title="Sao chép Channel ID">
                        <i class="fa-solid fa-copy"></i>
                    </button>
                </div>
            </td>
            <td data-col="col-country">
                ${getCountryBadge(c.country)}
            </td>
            <td data-col="col-subs">
                <div style="font-size:13px; font-weight:700; color:var(--text-primary);">${c.subscriber_count ? formatNumber(c.subscriber_count) : '<span class="text-muted">Ẩn</span>'}</div>
            </td>
            <td data-col="col-videos">
                <div style="font-size:12.5px; color:#cbd5e1;">${c.video_count ? c.video_count.toLocaleString() : 'N/A'}</div>
            </td>
            <td data-col="col-avg-views">
                <div style="font-size:13px; font-weight:700; color:#fff;">
                    ${c.avg_views ? formatNumber(c.avg_views) : '<span class="text-muted">N/A</span>'}
                </div>
            </td>
            <td data-col="col-total-views">
                <div style="font-size:12.5px; color:#cbd5e1;">${c.total_view_count ? formatNumber(c.total_view_count) : 'N/A'}</div>
            </td>
            <td data-col="col-ratio">
                ${ratioBadge || '<span class="text-muted" style="font-size:11px;">—</span>'}
            </td>
            <td data-col="col-last-upload">
                <div style="font-size:12px; font-weight:600; color:var(--text-primary);">${c.last_upload_date || 'N/A'}</div>
                <span class="text-muted" style="font-size:11px;">(${c.days_since_last_upload !== undefined && c.days_since_last_upload !== null ? c.days_since_last_upload : 0} ngày trước)</span>
            </td>
            <td data-col="col-cadence">
                <span class="badge ${c.upload_cadence_days > 0 && c.upload_cadence_days <= 1 ? 'badge-success' : 'badge-info'}" style="font-size:11px;">
                    ${escapeHtml(c.cadence_description || (c.upload_cadence_days > 0 ? c.upload_cadence_days + ' ngày/vid' : 'Chưa rõ'))}
                </span>
            </td>
            <td data-col="col-active">
                ${c.is_active
                ? '<span class="badge badge-success"><i class="fa-solid fa-circle-check"></i> Đang hoạt động</span>'
                : '<span class="badge badge-warning"><i class="fa-solid fa-clock-rotate-left"></i> Ít đăng</span>'}
            </td>
            <td data-col="col-actions">
                <div class="action-dropdown-wrap">
                    <button type="button" class="btn-more-actions" id="btn-more-${c.originalIndex}" 
                        onclick="toggleActionMenu(event, ${c.originalIndex})" 
                        title="Tùy chọn thao tác">
                        <i class="fa-solid fa-ellipsis"></i>
                    </button>
                    <div class="action-dropdown-menu" id="action-menu-${c.originalIndex}">
                        <button type="button" class="action-dropdown-item" onclick="openChannelDetailModal(${c.originalIndex})">
                            <i class="fa-solid fa-circle-info" style="color:var(--accent-cyan);"></i> Xem chi tiết
                        </button>
                        <button type="button" class="action-dropdown-item" onclick="openChannelVideosModal('${escapeHtml(cid)}', '${escapeHtml(c.title || '')}')">
                            <i class="fa-solid fa-film" style="color:#00f2fe;"></i> Chi Tiết Video
                        </button>
                        <button type="button" class="action-dropdown-item" onclick="toggleSaveFromMenu(${c.originalIndex})">
                            <i class="${c.is_saved ? 'fa-solid fa-trash-can text-danger' : 'fa-solid fa-bookmark text-gold'}"></i> 
                            <span>${c.is_saved ? 'Bỏ lưu kênh' : 'Lưu kênh'}</span>
                        </button>
                        <div class="dropdown-divider"></div>
                        <a href="${escapeHtml(channelUrl)}" target="_blank" rel="noopener" class="action-dropdown-item">
                            <i class="fa-brands fa-youtube" style="color:#ef4444;"></i> Mở YouTube
                        </a>
                        <button type="button" class="action-dropdown-item" onclick="copyTextToClipboard('${escapeHtml(cid)}', 'Đã sao chép Channel ID!')">
                            <i class="fa-solid fa-copy" style="color:#94a3b8;"></i> Sao chép ID
                        </button>
                    </div>
                </div>
            </td>
        </tr>
        `;
    }).join('');

    // Apply saved column visibility state
    applyColumnVisibility();
}

function updateHeaderSortIcons() {
    const fields = [
        { id: 'th-title', field: 'title' },
        { id: 'th-country', field: 'country' },
        { id: 'th-subs', field: 'subscriber_count' },
        { id: 'th-videos', field: 'video_count' },
        { id: 'th-avg-views', field: 'avg_views' },
        { id: 'th-total-views', field: 'total_view_count' },
        { id: 'th-ratio', field: 'views_per_sub_ratio' },
        { id: 'th-last_upload', field: 'days_since_last_upload' },
        { id: 'th-cadence', field: 'upload_cadence_days' },
        { id: 'th-active', field: 'is_active' }
    ];

    fields.forEach(item => {
        const th = document.getElementById(item.id);
        if (!th) return;
        const icon = th.querySelector('.sort-icon');
        if (currentSortField === item.field) {
            th.classList.add('sorted-active');
            if (icon) {
                icon.className = currentSortDirection === 'asc'
                    ? 'fa-solid fa-arrow-up-short-wide sort-icon'
                    : 'fa-solid fa-arrow-down-wide-short sort-icon';
            }
        } else {
            th.classList.remove('sorted-active');
            if (icon) icon.className = 'fa-solid fa-sort sort-icon';
        }
    });
}

function updateSortDirectionBtn() {
    const btn = document.getElementById('btnSortDirection');
    const icon = document.getElementById('sortDirIcon');
    const text = document.getElementById('sortDirText');
    if (!btn || !icon || !text) return;

    if (currentSortDirection === 'asc') {
        icon.className = 'fa-solid fa-arrow-up-wide-short';
        text.textContent = 'Tăng dần';
        btn.title = 'Hiện đang Tăng dần. Bấm để chuyển sang Giảm dần';
    } else {
        icon.className = 'fa-solid fa-arrow-down-wide-short';
        text.textContent = 'Giảm dần';
        btn.title = 'Hiện đang Giảm dần. Bấm để chuyển sang Tăng dần';
    }

    if (currentSortField === 'default') {
        btn.style.opacity = '0.45';
        btn.style.pointerEvents = 'none';
    } else {
        btn.style.opacity = '1';
        btn.style.pointerEvents = 'auto';
    }
}

function toggleSortDirection() {
    currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    updateSortDirectionBtn();
    renderYtChannelsTable();
}

function handleHeaderSort(field) {
    if (currentSortField === field) {
        currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortField = field;
        // Các trường số lượng thường ưu tiên xem từ cao xuống thấp trước
        if (['subscriber_count', 'video_count', 'avg_views', 'total_view_count', 'views_per_sub_ratio', 'is_active'].includes(field)) {
            currentSortDirection = 'desc';
        } else {
            currentSortDirection = 'asc';
        }
    }
    syncSortSelectUI();
    updateSortDirectionBtn();
    renderYtChannelsTable();
}

function handleSortSelectChange(field) {
    currentSortField = field;
    if (field !== 'default') {
        if (['subscriber_count', 'video_count', 'avg_views', 'total_view_count', 'views_per_sub_ratio', 'is_active'].includes(field)) {
            currentSortDirection = 'desc';
        } else {
            currentSortDirection = 'asc';
        }
    } else {
        currentSortDirection = 'asc';
    }
    updateSortDirectionBtn();
    renderYtChannelsTable();
}

function syncSortSelectUI() {
    const sel = document.getElementById('ytSortSelect');
    if (!sel) return;
    sel.value = currentSortField;
}

function handleFilterActiveChange(checked) {
    filterActiveOnly = checked;
    renderYtChannelsTable();
}

function handleFilterKeywordChange(val) {
    filterKeyword = val;
    renderYtChannelsTable();
}

function handleFilterSavedChange(val) {
    filterSaved = val;
    renderYtChannelsTable();
}

function handleSaveBtnHover(btn, isHover) {
    if (btn && btn.dataset.saved === 'true') {
        if (isHover) {
            btn.innerHTML = '<i class="fa-solid fa-xmark"></i> Bỏ Lưu';
        } else {
            btn.innerHTML = '<i class="fa-solid fa-check"></i> Đã Lưu';
        }
    }
}

async function toggleSaveChannel(origIdx) {
    const ch = rawYtChannels[origIdx];
    if (!ch) return;
    const btn = document.getElementById(`save-btn-${origIdx}`);
    const row = document.getElementById(`ch-row-${origIdx}`);

    if (ch.is_saved) {
        // --- BỎ LƯU (UNSAVE) ---
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Bỏ Lưu...';
        }
        try {
            const res = await fetch('/api/youtube/unsave-channel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel_id: ch.channel_id })
            });
            const data = await res.json();
            if (data.status === 'success') {
                ch.is_saved = false;
                showToast(`Đã bỏ lưu kênh "${ch.title}"!`);
                loadDashboardStats();
                renderYtChannelsTable();
            } else {
                showToast('Lỗi bỏ lưu kênh: ' + (data.message || 'Không rõ'), true);
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fa-solid fa-check"></i> Đã Lưu';
                }
            }
        } catch (err) {
            showToast('Lỗi bỏ lưu kênh: ' + err.message, true);
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-check"></i> Đã Lưu';
            }
        }
    } else {
        // --- LƯU KÊNH (SAVE) ---
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Lưu...';
        }
        try {
            await fetch('/api/youtube/save-channels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify([ch])
            });
            ch.is_saved = true;
            showToast(`Đã lưu kênh "${ch.title}" vào danh sách theo dõi!`);
            loadDashboardStats();
            renderYtChannelsTable();
        } catch (err) {
            showToast('Lỗi lưu kênh: ' + err.message, true);
            if (btn) {
                btn.disabled = false;
                btn.className = 'btn btn-sm btn-secondary';
                btn.dataset.saved = 'false';
                btn.innerHTML = '<i class="fa-solid fa-bookmark"></i> Lưu Kênh';
            }
        }
    }
}

// Giữ tương thích nếu có code gọi saveSingleChannel
function saveSingleChannel(ch, rowIdx) {
    toggleSaveChannel(rowIdx);
}

// ==========================================================================
// Action Dropdown & Channel Detail Modal Management
// ==========================================================================
let activeDetailChannel = null;

// Tracks original parent so we can return teleported menus
const _menuOriginalParent = new Map();

function closeAllActionMenus() {
    document.querySelectorAll('.action-dropdown-menu.show').forEach(m => {
        m.classList.remove('show');
        m.style.top = '';
        m.style.bottom = '';
        m.style.left = '';
        // Restore to original parent if teleported
        const originalParent = _menuOriginalParent.get(m.id);
        if (originalParent && m.parentElement === document.body) {
            originalParent.appendChild(m);
        }
        _menuOriginalParent.delete(m.id);
    });
    document.querySelectorAll('.btn-more-actions.active').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.action-dropdown-wrap.active').forEach(w => w.classList.remove('active'));
    document.querySelectorAll('tr.row-dropdown-open').forEach(r => r.classList.remove('row-dropdown-open'));
}

function toggleActionMenu(e, id) {
    e.stopPropagation();
    const menu = document.getElementById(`action-menu-${id}`);
    const btn = document.getElementById(`btn-more-${id}`);
    const row = (btn ? btn.closest('tr') : null) || document.getElementById(`ch-row-${id}`);
    if (!menu) return;

    const isOpen = menu.classList.contains('show');
    closeAllActionMenus();

    if (!isOpen && btn) {
        if (btn) btn.classList.add('active');
        const wrap = btn ? btn.closest('.action-dropdown-wrap') : null;
        if (wrap) wrap.classList.add('active');
        if (row) row.classList.add('row-dropdown-open');

        const rect = btn.getBoundingClientRect();
        const menuWidth = 185;
        const spaceBelow = window.innerHeight - rect.bottom;
        const spaceAbove = rect.top;

        // Teleport to body to escape table overflow/transform stacking context
        _menuOriginalParent.set(menu.id, menu.parentElement);
        document.body.appendChild(menu);

        menu.style.position = 'fixed';
        menu.style.minWidth = menuWidth + 'px';
        menu.style.left = Math.max(4, rect.right - menuWidth) + 'px';
        menu.style.top = '';
        menu.style.bottom = '';

        if (spaceBelow < 260 && spaceAbove > spaceBelow) {
            menu.style.bottom = (window.innerHeight - rect.top + 4) + 'px';
            menu.classList.add('dropup');
        } else {
            menu.style.top = (rect.bottom + 4) + 'px';
            menu.classList.remove('dropup');
        }

        menu.classList.add('show');
    }
}

function toggleSaveFromMenu(index) {
    closeAllActionMenus();
    toggleSaveChannel(index);
}

async function openChannelDetailModal(target) {
    closeAllActionMenus();
    let ch = null;
    if (typeof target === 'number') {
        ch = rawYtChannels[target];
    } else if (typeof target === 'string') {
        ch = rawYtChannels.find(c => c.channel_id === target) ||
            cachedSavedChannels.find(c => c.channel_id === target);
        // If not found in memory, fetch from backend API
        if (!ch) {
            try {
                const res = await fetch(`/api/youtube/channels/${encodeURIComponent(target)}`);
                if (res.ok) {
                    ch = await res.json();
                }
            } catch (err) {
                console.warn('Cannot fetch channel detail:', err);
            }
        }
    } else if (target && typeof target === 'object') {
        ch = target;
    }

    if (!ch) {
        showToast('Không tìm thấy thông tin kênh!', true);
        return;
    }

    activeDetailChannel = ch;

    const modal = document.getElementById('channelDetailModal');
    if (!modal) return;

    // Header & Hero
    const elAvatar = document.getElementById('detailChannelAvatar');
    const elFallback = document.getElementById('detailAvatarFallback');
    if (ch.thumbnail_url) {
        elAvatar.src = ch.thumbnail_url;
        elAvatar.style.display = 'block';
        elFallback.style.display = 'none';
        elAvatar.onerror = () => {
            elAvatar.style.display = 'none';
            elFallback.style.display = 'flex';
        };
    } else {
        elAvatar.style.display = 'none';
        elFallback.style.display = 'flex';
    }

    const elTitle = document.getElementById('detailChannelTitle');
    if (elTitle) elTitle.textContent = ch.title || 'Kênh YouTube';

    const elActiveBadge = document.getElementById('detailChannelActiveBadge');
    if (elActiveBadge) {
        if (ch.is_active) {
            elActiveBadge.className = 'badge badge-success';
            elActiveBadge.innerHTML = '<i class="fa-solid fa-circle-check"></i> Đang hoạt động';
        } else {
            elActiveBadge.className = 'badge badge-warning';
            elActiveBadge.innerHTML = '<i class="fa-solid fa-clock-rotate-left"></i> Ít đăng bài';
        }
    }

    const elHandle = document.getElementById('detailChannelHandle');
    if (elHandle) {
        elHandle.textContent = ch.handle ? ch.handle : '';
        elHandle.style.display = ch.handle ? 'inline-block' : 'none';
    }

    const elId = document.getElementById('detailChannelId');
    if (elId) elId.textContent = ch.channel_id || 'N/A';

    const btnCopy = document.getElementById('btnCopyDetailId');
    if (btnCopy) {
        btnCopy.onclick = () => copyTextToClipboard(ch.channel_id || '', 'Đã sao chép Channel ID!');
    }

    const elCountry = document.getElementById('detailChannelCountry');
    if (elCountry) {
        elCountry.innerHTML = getCountryBadge(ch.country);
    }

    const elJoined = document.getElementById('detailChannelJoined');
    if (elJoined) {
        if (ch.created_at) {
            let dStr = ch.created_at;
            try {
                const dt = new Date(ch.created_at);
                if (!isNaN(dt.getTime())) {
                    dStr = dt.toLocaleDateString('vi-VN');
                }
            } catch (e) { }
            elJoined.innerHTML = `<i class="fa-regular fa-calendar"></i> Tham gia: ${dStr}`;
            elJoined.style.display = 'inline-flex';
        } else {
            elJoined.style.display = 'none';
        }
    }

    const ytLink = document.getElementById('detailChannelYtLink');
    if (ytLink) {
        const url = ch.url || (ch.channel_id ? `https://www.youtube.com/channel/${ch.channel_id}` : '#');
        ytLink.href = url;
    }

    // Update Save button state
    updateDetailModalSaveBtn();

    // 8 KPI Stat Cards
    const elSubs = document.getElementById('detailSubs');
    if (elSubs) elSubs.textContent = ch.subscriber_count ? formatNumber(ch.subscriber_count) : 'Ẩn / Chưa rõ';

    const elVideos = document.getElementById('detailVideos');
    if (elVideos) elVideos.textContent = ch.video_count ? ch.video_count.toLocaleString() : 'N/A';

    const elAvgViews = document.getElementById('detailAvgViews');
    if (elAvgViews) elAvgViews.textContent = ch.avg_views ? formatNumber(ch.avg_views) : 'N/A';

    const elTotalViews = document.getElementById('detailTotalViews');
    if (elTotalViews) elTotalViews.textContent = ch.total_view_count ? formatNumber(ch.total_view_count) : 'N/A';

    const elRatio = document.getElementById('detailRatio');
    if (elRatio) {
        const r = ch.views_per_sub_ratio || 0;
        if (r > 0) {
            const fire = r >= 1.0 ? '🔥 ' : '';
            elRatio.textContent = `${fire}${r.toFixed(2)}x`;
            elRatio.style.color = r >= 2.0 ? '#f87171' : (r >= 1.0 ? '#fbbf24' : '#38bdf8');
        } else {
            elRatio.textContent = '—';
            elRatio.style.color = 'var(--text-muted)';
        }
    }

    const elCadence = document.getElementById('detailCadence');
    if (elCadence) {
        elCadence.textContent = ch.cadence_description || (ch.upload_cadence_days > 0 ? `${ch.upload_cadence_days} ngày/vid` : 'Chưa rõ');
    }

    const elLastUpload = document.getElementById('detailLastUpload');
    if (elLastUpload) {
        const days = ch.days_since_last_upload !== undefined && ch.days_since_last_upload !== null ? `${ch.days_since_last_upload} ngày trước` : '';
        elLastUpload.textContent = ch.last_upload_date ? `${ch.last_upload_date} ${days ? `(${days})` : ''}` : 'N/A';
    }

    const elStatus = document.getElementById('detailStatus');
    if (elStatus) {
        elStatus.textContent = ch.is_active ? '🟢 Hoạt động' : '⚪ Ít hoạt động';
        elStatus.style.color = ch.is_active ? '#34d399' : '#94a3b8';
    }

    // Description
    const elDesc = document.getElementById('detailDescription');
    if (elDesc) {
        const descText = (ch.description || '').trim();
        if (descText) {
            elDesc.textContent = descText;
            elDesc.classList.remove('detail-no-data');
        } else {
            elDesc.textContent = 'Kênh này chưa có mô tả hoặc chưa được cập nhật từ YouTube.';
            elDesc.classList.add('detail-no-data');
        }
    }

    // Keywords / Tags
    const elKwWrap = document.getElementById('detailKeywordsList');
    if (elKwWrap) {
        let kwList = [];
        if (Array.isArray(ch.keywords)) {
            kwList = ch.keywords;
        } else if (typeof ch.keywords === 'string') {
            try {
                const parsed = JSON.parse(ch.keywords);
                if (Array.isArray(parsed)) kwList = parsed;
                else kwList = ch.keywords.split(',').map(s => s.trim()).filter(Boolean);
            } catch (e) {
                kwList = ch.keywords.split(',').map(s => s.trim()).filter(Boolean);
            }
        }
        if (kwList && kwList.length > 0) {
            elKwWrap.innerHTML = kwList.map(kw => `<span class="detail-tag-chip"><i class="fa-solid fa-tag"></i> ${escapeHtml(kw)}</span>`).join('');
        } else {
            elKwWrap.innerHTML = '<span class="detail-no-data">Không có thẻ từ khóa nào.</span>';
        }
    }

    // Topics
    const elTopWrap = document.getElementById('detailTopicsList');
    if (elTopWrap) {
        let topList = [];
        if (Array.isArray(ch.topic_categories)) {
            topList = ch.topic_categories;
        } else if (typeof ch.topic_categories === 'string') {
            try {
                const parsed = JSON.parse(ch.topic_categories);
                if (Array.isArray(parsed)) topList = parsed;
            } catch (e) { }
        }
        if (topList && topList.length > 0) {
            elTopWrap.innerHTML = topList.map(t => {
                let clean = t;
                if (typeof t === 'string' && t.includes('/wiki/')) {
                    clean = decodeURIComponent(t.split('/wiki/')[1].replace(/_/g, ' '));
                }
                return `<span class="detail-topic-chip"><i class="fa-solid fa-shapes"></i> ${escapeHtml(clean)}</span>`;
            }).join('');
        } else {
            elTopWrap.innerHTML = '<span class="detail-no-data">Không có danh mục chủ đề cụ thể.</span>';
        }
    }

    // Recent Videos List
    const elRecentSec = document.getElementById('detailRecentVideosSection');
    const elRecentList = document.getElementById('detailRecentVideosList');
    const elRecentBadge = document.getElementById('detailRecentVideosCount');
    let recentVids = [];
    if (Array.isArray(ch.recent_video_titles)) {
        recentVids = ch.recent_video_titles;
    } else if (typeof ch.recent_video_titles === 'string') {
        try {
            const parsed = JSON.parse(ch.recent_video_titles);
            if (Array.isArray(parsed)) recentVids = parsed;
        } catch (e) { }
    }
    if (recentVids && recentVids.length > 0) {
        if (elRecentSec) elRecentSec.style.display = 'block';
        if (elRecentBadge) elRecentBadge.textContent = `${recentVids.length} Video`;
        if (elRecentList) {
            elRecentList.innerHTML = recentVids.map(title => {
                const searchQ = encodeURIComponent(title + ' ' + (ch.title || ''));
                const ytUrl = `https://www.youtube.com/results?search_query=${searchQ}`;
                return `
                <a href="${ytUrl}" target="_blank" rel="noopener" class="detail-video-item" title="Bấm để mở video trên YouTube: ${escapeHtml(title)}">
                    <i class="fa-brands fa-youtube" style="color:#ef4444; font-size:15px;"></i>
                    <span class="detail-video-item-title">${escapeHtml(title)}</span>
                    <i class="fa-solid fa-arrow-up-right-from-square detail-video-link-icon"></i>
                </a>
                `;
            }).join('');
        }
    } else {
        if (elRecentSec) elRecentSec.style.display = 'none';
    }

    // Similar Channels
    renderSimilarChannels(ch);

    // Show modal
    modal.classList.add('active');
    modal.classList.add('show');
}

function closeChannelDetailModal() {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
        document.activeElement.blur();
    }
    const modal = document.getElementById('channelDetailModal');
    if (modal) {
        modal.classList.remove('active');
        modal.classList.remove('show');
    }
    activeDetailChannel = null;
}

async function openChannelVideosModal(channelId, channelTitle = '') {
    closeAllActionMenus();
    const modal = document.getElementById('modalChannelVideos');
    const titleEl = document.getElementById('modalChannelVideosTitle');
    const subEl = document.getElementById('modalChannelVideosSub');
    const bodyEl = document.getElementById('modalChannelVideosBody');
    const statsEl = document.getElementById('modalChannelVideosStats');

    if (titleEl) {
        titleEl.innerHTML = `<i class="fa-solid fa-film text-cyan"></i> Video Kênh: ${escapeHtml(channelTitle || channelId)}`;
    }
    if (subEl) {
        subEl.textContent = `Danh sách video của kênh ID: ${channelId}`;
    }
    if (bodyEl) {
        bodyEl.innerHTML = '<div class="text-center py-5 text-muted"><i class="fa-solid fa-spinner fa-spin text-cyan" style="font-size:24px;"></i><p class="mt-2" style="font-size:12px;">Đang tải danh sách video của kênh...</p></div>';
    }
    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('active');
    }

    try {
        const res = await fetch(`/api/channels/${encodeURIComponent(channelId)}/videos`);
        const data = await res.json();
        const vids = data.videos || [];
        if (statsEl) statsEl.textContent = `${vids.length} Video`;

        if (!vids.length) {
            bodyEl.innerHTML = `
                <div style="text-align:center; padding:36px 20px; background:rgba(255,255,255,0.02); border-radius:10px; border:1px dashed rgba(255,255,255,0.1);">
                    <i class="fa-solid fa-video-slash text-cyan" style="font-size:32px; opacity:0.6; margin-bottom:10px; display:block;"></i>
                    <div style="font-size:14px; font-weight:700; color:#fff;">Kênh này chưa có video nào được tải về</div>
                    <div style="font-size:12px; color:var(--text-muted); margin-top:4px;">
                        Bấm nút "Quét video mới ngay" trong menu thao tác để tải video mới nhất từ RSS YouTube.
                    </div>
                </div>
            `;
            return;
        }

        bodyEl.innerHTML = `
            <div style="display:flex; flex-direction:column; gap:10px;">
                ${vids.map(v => {
                    const isRendered = v.has_rendered || v.status === 'rendered' || (v.rendered_parts && v.rendered_parts.length > 0);
                    const isRendering = v.status === 'rendering';
                    
                    let renderBadge = '';
                    if (isRendering) {
                        renderBadge = '<span class="badge badge-purple" style="font-size:11px;" title="Video đang trong tiến trình xử lý render"><i class="fa-solid fa-spinner fa-spin"></i> Đang render AI...</span>';
                    } else if (isRendered) {
                        const partsText = (v.rendered_parts && v.rendered_parts.length > 1) ? `${v.rendered_parts.length} Parts (9:16)` : 'Đã Render 9:16';
                        renderBadge = `<span class="badge badge-success" style="font-size:11px;" title="Video dọc 9:16 đã render hoàn tất"><i class="fa-solid fa-circle-check"></i> ${partsText}</span>`;
                    } else {
                        renderBadge = '<span class="badge badge-secondary" style="font-size:11px;" title="Chưa tạo bản cắt 9:16 cho video này"><i class="fa-solid fa-hourglass-half"></i> Chưa render</span>';
                    }

                    const dlBadge = v.has_raw || v.download_path
                        ? `<span class="badge badge-blue" style="font-size:11px;" title="Đã lưu video MP4 gốc trên máy"><i class="fa-solid fa-cloud-arrow-down"></i> Đã tải MP4 gốc</span>`
                        : '<span class="badge badge-secondary" style="font-size:11px;" title="Chưa có file MP4 gốc">Chưa có MP4</span>';

                    let partsHtml = '';
                    if (v.rendered_parts && v.rendered_parts.length > 0) {
                        partsHtml = `
                            <div style="display:flex; gap:5px; flex-wrap:wrap; margin-top:5px;">
                                <span style="font-size:10.5px; color:var(--text-muted); align-self:center;">Parts:</span>
                                ${v.rendered_parts.map(p => `
                                    <span class="badge badge-purple" style="font-size:10px; padding:2px 8px; border-radius:4px;" title="Bản render Part ${p.part} (dọc 9:16)">Part ${p.part}</span>
                                `).join('')}
                            </div>
                        `;
                    }

                    return `
                        <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.07); border-radius:10px; padding:12px 16px; display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;">
                            <div style="flex:1; min-width:240px; max-width:440px;">
                                <div style="display:flex; align-items:center; gap:8px; font-size:11px; color:var(--text-muted); margin-bottom:4px;">
                                    <span>ID: <code>${v.yt_video_id || '#' + v.id}</code></span>
                                    <span>•</span>
                                    <span><i class="fa-solid fa-clock"></i> ${v.duration || 65}s</span>
                                    <span>•</span>
                                    <span>${v.created_at ? v.created_at.substring(0, 16) : ''}</span>
                                </div>
                                <h5 style="margin:0; font-size:13px; color:#fff; font-weight:600; line-height:1.4; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:440px;" title="${escapeHtml(v.title || '')}">
                                    ${escapeHtml(v.title || 'Video #' + v.id)}
                                </h5>
                                ${partsHtml}
                            </div>
                            <div style="display:flex; flex-direction:column; gap:4px; align-items:flex-start; min-width:130px;">
                                ${dlBadge}
                                ${renderBadge}
                            </div>
                            <div style="display:flex; align-items:center; gap:8px;">
                                <button type="button" class="btn btn-secondary btn-sm" onclick="switchTab('tab-video-studio'); selectStudioVideo('${v.yt_video_id || v.id}'); closeChannelVideosModal();" title="Mở video này trong Studio Biên Tập">
                                    <i class="fa-solid fa-wand-magic-sparkles text-cyan"></i>
                                </button>
                                <button type="button" class="btn btn-danger btn-sm" onclick="deleteChannelVideoModalItem('${v.yt_video_id || v.id}', '${escapeHtml(channelId)}', '${escapeHtml(v.title || '')}')" title="Xóa video này và dọn dẹp file">
                                    <i class="fa-solid fa-trash-can"></i> Xóa
                                </button>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    } catch (err) {
        bodyEl.innerHTML = `<div class="text-center py-4 text-danger"><i class="fa-solid fa-circle-exclamation"></i> Lỗi nạp video: ${escapeHtml(err.message)}</div>`;
    }
}

function closeChannelVideosModal() {
    const modal = document.getElementById('modalChannelVideos');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('active');
    }
}

async function deleteChannelVideoModalItem(videoId, channelId, videoTitle) {
    const confirmed = await showConfirmDialog({
        title: 'Xác Nhận Xóa Video',
        message: `Bạn có chắc muốn xóa video "${videoTitle || videoId}"?`,
        details: 'File video gốc và toàn bộ các Part 9:16 đã render trên ổ đĩa sẽ bị xóa vĩnh viễn.',
        confirmText: 'Xác Nhận Xóa',
        confirmClass: 'btn-danger'
    });
    if (!confirmed) return;

    showToast('Đang xóa video và file đĩa...');
    try {
        const res = await fetch(`/api/video/${videoId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast('✅ ' + (data.message || 'Đã xóa video thành công!'), 'success');
            // Reload modal videos
            openChannelVideosModal(channelId, '');
            // Reload channels table to update badge counts
            loadSavedChannels();
            loadVideos();
            loadStudioVideos();
        } else {
            showToast('Lỗi khi xóa video: ' + (data.detail || data.message || 'Không xác định'), 'error');
        }
    } catch (err) {
        showToast('Lỗi kết nối khi xóa: ' + err.message, 'error');
    }
}

function updateDetailModalSaveBtn() {
    const btn = document.getElementById('btnToggleSaveFromDetail');
    if (!btn || !activeDetailChannel) return;

    if (activeDetailChannel.is_saved) {
        btn.className = 'btn btn-secondary btn-sm';
        btn.innerHTML = '<i class="fa-solid fa-check text-success"></i> <span id="detailSaveBtnText">Đã Lưu Kênh</span>';
    } else {
        btn.className = 'btn btn-primary btn-sm';
        btn.innerHTML = '<i class="fa-solid fa-bookmark"></i> <span id="detailSaveBtnText">Lưu Kênh</span>';
    }
}

async function toggleSaveFromDetailModal() {
    if (!activeDetailChannel) return;
    const ch = activeDetailChannel;
    const cid = ch.channel_id;

    if (ch.is_saved) {
        try {
            const res = await fetch('/api/youtube/unsave-channel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel_id: cid })
            });
            const data = await res.json();
            if (data.status === 'success') {
                ch.is_saved = false;
                const raw = rawYtChannels.find(c => c.channel_id === cid);
                if (raw) raw.is_saved = false;
                showToast(`Đã bỏ lưu kênh "${ch.title}"!`);
                updateDetailModalSaveBtn();
                renderYtChannelsTable();
                loadDashboardStats();
                renderSimilarChannels(ch);
            } else {
                showToast('Lỗi khi bỏ lưu: ' + (data.message || 'Thất bại'), true);
            }
        } catch (err) {
            showToast('Lỗi kết nối: ' + err.message, true);
        }
    } else {
        try {
            await fetch('/api/youtube/save-channels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify([ch])
            });
            ch.is_saved = true;
            const raw = rawYtChannels.find(c => c.channel_id === cid);
            if (raw) raw.is_saved = true;
            showToast(`Đã lưu kênh "${ch.title}"!`);
            updateDetailModalSaveBtn();
            renderYtChannelsTable();
            loadDashboardStats();
            renderSimilarChannels(ch);
        } catch (err) {
            showToast('Lỗi khi lưu kênh: ' + err.message, true);
        }
    }
}

function renderSimilarChannels(target) {
    const grid = document.getElementById('similarChannelsGrid');
    const badge = document.getElementById('similarChannelsBadge');
    if (!grid) return;

    const pool = [...rawYtChannels];
    cachedSavedChannels.forEach(sc => {
        if (!pool.some(p => p.channel_id === sc.channel_id)) {
            pool.push(sc);
        }
    });

    const others = pool.filter(c => c.channel_id !== target.channel_id);
    if (!others.length) {
        grid.innerHTML = '<div class="card-empty-state" style="grid-column: 1/-1;"><p>Chưa có kênh tương đồng nào trong dữ liệu quét hiện tại.</p></div>';
        if (badge) badge.textContent = '0 Kênh';
        return;
    }

    const targetCountry = (target.country || '').toUpperCase();
    const targetSubs = target.subscriber_count || 0;
    const targetWords = (target.title || '').toLowerCase().split(/\s+/).filter(w => w.length > 2);

    let targetKw = [];
    if (Array.isArray(target.keywords)) targetKw = target.keywords;
    else if (typeof target.keywords === 'string') {
        try { targetKw = JSON.parse(target.keywords); } catch (e) { targetKw = target.keywords.split(','); }
    }
    targetKw = targetKw.map(k => String(k).toLowerCase().trim()).filter(Boolean);

    const scored = others.map(other => {
        let score = 0;
        // Country match
        if (targetCountry && (other.country || '').toUpperCase() === targetCountry) {
            score += 4;
        }
        // Keywords match
        let otherKw = [];
        if (Array.isArray(other.keywords)) otherKw = other.keywords;
        else if (typeof other.keywords === 'string') {
            try { otherKw = JSON.parse(other.keywords); } catch (e) { otherKw = other.keywords.split(','); }
        }
        otherKw = otherKw.map(k => String(k).toLowerCase().trim()).filter(Boolean);
        for (const k of targetKw) {
            if (otherKw.includes(k)) score += 3;
        }
        // Title words match
        const otherTitleLower = (other.title || '').toLowerCase();
        for (const w of targetWords) {
            if (otherTitleLower.includes(w)) score += 2;
        }
        // Viral Ratio similarity
        if (target.views_per_sub_ratio && other.views_per_sub_ratio) {
            const diff = Math.abs(target.views_per_sub_ratio - other.views_per_sub_ratio);
            if (diff <= 0.5) score += 3;
        }
        // Subs range
        if (targetSubs > 0 && other.subscriber_count > 0) {
            const ratio = other.subscriber_count / targetSubs;
            if (ratio >= 0.4 && ratio <= 2.5) score += 2;
        }
        if (other.is_active) score += 1;

        return { channel: other, score };
    });

    scored.sort((a, b) => b.score - a.score);
    const topSimilar = scored.slice(0, 9).map(s => s.channel);

    if (badge) badge.textContent = `${topSimilar.length} Kênh gợi ý`;

    grid.innerHTML = topSimilar.map(c => {
        const thumb = c.thumbnail_url
            ? `<img src="${c.thumbnail_url}" alt="" class="similar-avatar" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
               <div class="similar-avatar-fallback" style="display:none;"><i class="fa-brands fa-youtube"></i></div>`
            : `<div class="similar-avatar-fallback"><i class="fa-brands fa-youtube"></i></div>`;
        const r = c.views_per_sub_ratio || 0;
        const fire = r >= 1.0 ? '🔥 ' : '';
        const ratioText = r > 0 ? `${fire}${r.toFixed(2)}x` : '—';

        return `
            <div class="similar-channel-card">
                <div class="similar-card-top">
                    ${thumb}
                    <div class="similar-meta">
                        <div class="similar-title" onclick="openChannelDetailModal('${escapeHtml(c.channel_id)}')" title="${escapeHtml(c.title)}">
                            ${escapeHtml(c.title)}
                        </div>
                        <div class="similar-handle">
                            ${c.handle ? escapeHtml(c.handle) : escapeHtml(c.channel_id)}
                        </div>
                    </div>
                    ${getCountryBadge(c.country)}
                </div>

                <div class="similar-metrics-row">
                    <div class="similar-metric-item">
                        <span class="similar-metric-label">Subscribers</span>
                        <span class="similar-metric-val">${c.subscriber_count ? formatNumber(c.subscriber_count) : 'Ẩn'}</span>
                    </div>
                    <div class="similar-metric-item">
                        <span class="similar-metric-label">Lượt Xem TB</span>
                        <span class="similar-metric-val">${c.avg_views ? formatNumber(c.avg_views) : 'N/A'}</span>
                    </div>
                    <div class="similar-metric-item">
                        <span class="similar-metric-label">Viral Ratio</span>
                        <span class="similar-metric-val" style="color:${r >= 2.0 ? '#f87171' : (r >= 1.0 ? '#fbbf24' : '#38bdf8')};">${ratioText}</span>
                    </div>
                </div>

                <div class="similar-card-actions">
                    <button type="button" class="btn btn-secondary btn-sm" onclick="openChannelDetailModal('${escapeHtml(c.channel_id)}')">
                        <i class="fa-solid fa-circle-info text-cyan"></i> Chi tiết
                    </button>
                    <button type="button" class="btn btn-sm ${c.is_saved ? 'btn-saved' : 'btn-primary'}" onclick="toggleSaveChannelById('${escapeHtml(c.channel_id)}')">
                        ${c.is_saved ? '<i class="fa-solid fa-check"></i> Đã Lưu' : '<i class="fa-solid fa-bookmark"></i> Lưu Kênh'}
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

async function toggleSaveChannelById(channelId) {
    const rawIdx = rawYtChannels.findIndex(c => c.channel_id === channelId);
    if (rawIdx !== -1) {
        await toggleSaveChannel(rawIdx);
        if (activeDetailChannel) {
            updateDetailModalSaveBtn();
            renderSimilarChannels(activeDetailChannel);
        }
        return;
    }
    const saved = cachedSavedChannels.find(c => c.channel_id === channelId);
    if (saved) {
        try {
            const res = await fetch('/api/youtube/unsave-channel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel_id: channelId })
            });
            const data = await res.json();
            if (data.status === 'success') {
                showToast(`Đã bỏ lưu kênh!`);
                await loadSavedChannels();
                loadDashboardStats();
                if (activeDetailChannel) {
                    if (activeDetailChannel.channel_id === channelId) {
                        activeDetailChannel.is_saved = false;
                        updateDetailModalSaveBtn();
                    }
                    renderSimilarChannels(activeDetailChannel);
                }
            }
        } catch (e) {
            showToast('Lỗi: ' + e.message, true);
        }
    }
}

async function loadSavedChannels() {
    try {
        const res = await fetch('/api/youtube/channels');
        const channels = await res.json();
        // Cập nhật giao diện nếu cần
    } catch (err) { }
}

// 3. AI Video Editor
async function downloadSingleVideo() {
    const inputEl = document.getElementById('directDownloadUrl');
    const url = inputEl ? inputEl.value.trim() : '';
    const btn = document.getElementById('btnDownloadVideo');
    if (!url) {
        markInputError('directDownloadUrl', 'Vui lòng nhập link video YouTube hoặc Video ID!');
        return;
    }
    if (!isValidYouTubeUrl(url)) {
        markInputError('directDownloadUrl', 'Định dạng link YouTube không hợp lệ! Vui lòng nhập link watch, shorts hoặc video ID 11 ký tự.');
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Tải...';
    }
    showToast('Đang tải video gốc trong nền...');
    try {
        const res = await fetch('/api/video/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, is_studio: true })
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast('Tải video thành công!', 'success');
            if (inputEl) inputEl.value = '';
            loadVideos();
            loadStudioVideos();
            loadDashboardStats();
        } else {
            showToast('Lỗi: ' + (data.detail || data.message || 'Không xác định'), 'error');
        }
    } catch (err) {
        showToast('Lỗi tải video: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-download"></i> Tải Video Gốc';
        }
    }
}

async function loadVideos() {
    const tbody = document.getElementById('videosTableBody');
    try {
        const res = await fetch('/api/video/list');
        const videos = await res.json();
        cachedVideos = videos;

        if (videos.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">Chưa có video nào được tải về. Dán link phía trên để tải thử!</td></tr>`;
            return;
        }

        tbody.innerHTML = videos.map(v => `
            <tr>
                <td><code>#${v.id}</code></td>
                <td>
                    <div class="table-text-truncate" style="max-width: 250px;" title="${escapeHtml(v.title)}">
                        <strong>${escapeHtml(v.title)}</strong>
                    </div>
                    <span class="text-muted" style="font-size:11px;">ID: ${v.yt_video_id}</span>
                </td>
                <td>${v.duration}s</td>
                <td>
                    ${v.status === 'rendered'
                ? '<span class="badge badge-success"><i class="fa-solid fa-check-double"></i> Đã Render AI 9:16</span>'
                : '<span class="badge badge-warning">Video Gốc</span>'}
                </td>
                <td>
                    <div style="display:flex; gap:6px;">
                        <button class="btn btn-sm btn-primary" onclick="renderVideoAI('${v.yt_video_id}', this)">
                            <i class="fa-solid fa-wand-magic-sparkles"></i> Render AI 9:16
                        </button>
                        ${v.rendered_path ? `
                        <button class="btn btn-sm btn-secondary" onclick="openUploadModal('${v.id}')">
                            <i class="fa-solid fa-cloud-arrow-up"></i> Đăng GPM
                        </button>
                        ` : ''}
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('Lỗi nạp video:', err);
    }
}

async function renderVideoAI(ytVideoId, btn) {
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Render...';
    }
    showToast('Đang tiến hành AI Render (Format 9:16, lật hình, đổi speed & cắt part)...');
    try {
        const res = await fetch('/api/video/render', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                video_id: ytVideoId,
                duration: 65,
                flip_horizontal: true,
                speed_factor: 1.03
            })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Render AI thành công! Video đã sẵn sàng đăng.');
            loadVideos();
            loadDashboardStats();
        } else {
            showToast('Lỗi render: ' + (data.detail || 'Không xác định'), true);
        }
    } catch (err) {
        showToast('Lỗi render: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Render AI 9:16';
        }
    }
}

// 4. GPMLogin Profiles
async function syncGPMProfiles(btn) {
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Đồng Bộ...';
    }
    showToast('Đang đồng bộ profiles từ GPMLogin Local API (:19995)...');
    try {
        const res = await fetch('/api/gpm/sync', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(`Đồng bộ thành công ${data.synced} profiles từ GPMLogin!`);
            loadGpmProfiles();
            loadDashboardStats();
        } else {
            showToast(data.message, true);
        }
    } catch (err) {
        showToast('Không kết nối được GPMLogin: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// ==========================================
// 4. GPMLOGIN PROFILES & TIKTOK TRACKER
// ==========================================
// ==========================================
// 4. GPMLOGIN PROFILES & TIKTOK TRACKER
// ==========================================
let gpmSortField = 'followers_count';
let gpmSortDirection = 'desc';

async function loadGpmProfiles() {
    try {
        const res = await fetch('/api/gpm/profiles');
        const profiles = await res.json();
        cachedGpmProfiles = profiles;
        renderGpmProfilesTable();
    } catch (err) {
        console.error('Lỗi nạp profiles:', err);
    }
}

function handleGpmSortChange(val) {
    gpmSortField = val;
    renderGpmProfilesTable();
}

function toggleGpmSortDirection() {
    gpmSortDirection = gpmSortDirection === 'asc' ? 'desc' : 'asc';
    const icon = document.getElementById('gpmSortDirIcon');
    const text = document.getElementById('gpmSortDirText');
    if (icon) icon.className = gpmSortDirection === 'asc' ? 'fa-solid fa-arrow-up-wide-short' : 'fa-solid fa-arrow-down-wide-short';
    if (text) text.textContent = gpmSortDirection === 'asc' ? 'Tăng dần' : 'Giảm dần';
    renderGpmProfilesTable();
}

function handleGpmHeaderSort(field) {
    if (gpmSortField === field) {
        gpmSortDirection = gpmSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        gpmSortField = field;
        gpmSortDirection = (field === 'followers_count' || field === 'eligible_10k') ? 'desc' : 'asc';
    }
    const select = document.getElementById('sortGpmField');
    if (select) select.value = gpmSortField;
    const icon = document.getElementById('gpmSortDirIcon');
    const text = document.getElementById('gpmSortDirText');
    if (icon) icon.className = gpmSortDirection === 'asc' ? 'fa-solid fa-arrow-up-wide-short' : 'fa-solid fa-arrow-down-wide-short';
    if (text) text.textContent = gpmSortDirection === 'asc' ? 'Tăng dần' : 'Giảm dần';
    renderGpmProfilesTable();
}

function resetGpmFilters() {
    gpmSortField = 'followers_count';
    gpmSortDirection = 'desc';
    const sortSel = document.getElementById('sortGpmField');
    if (sortSel) sortSel.value = 'followers_count';
    const filter10k = document.getElementById('filterGpm10k');
    if (filter10k) filter10k.value = 'all';
    const filterNotify = document.getElementById('filterGpmNotify');
    if (filterNotify) filterNotify.value = 'all';
    const filterNick = document.getElementById('filterGpmNick');
    if (filterNick) filterNick.value = 'all';
    const searchKw = document.getElementById('searchGpmKeyword');
    if (searchKw) searchKw.value = '';
    const icon = document.getElementById('gpmSortDirIcon');
    const text = document.getElementById('gpmSortDirText');
    if (icon) icon.className = 'fa-solid fa-arrow-down-wide-short';
    if (text) text.textContent = 'Giảm dần';
    renderGpmProfilesTable();
}

function exportGpmProfilesCsv() {
    const filter10k = document.getElementById('filterGpm10k')?.value || 'all';
    const filterNotify = document.getElementById('filterGpmNotify')?.value || 'all';
    const filterNick = document.getElementById('filterGpmNick')?.value || 'all';
    const keyword = (document.getElementById('searchGpmKeyword')?.value || '').trim().toLowerCase();

    let list = (cachedGpmProfiles || []).slice();

    if (filter10k === '10k') {
        list = list.filter(p => Boolean(p.eligible_10k === 1 || (p.followers_count || 0) >= 10000));
    } else if (filter10k === 'growing') {
        list = list.filter(p => !Boolean(p.eligible_10k === 1 || (p.followers_count || 0) >= 10000));
    }

    if (filterNotify === 'tracking') {
        list = list.filter(p => (p.notify_status || 'tracking').toLowerCase() === 'tracking');
    } else if (filterNotify === 'sent') {
        list = list.filter(p => (p.notify_status || '').toLowerCase() === 'sent');
    } else if (filterNotify === 'muted') {
        list = list.filter(p => (p.notify_status || '').toLowerCase() === 'muted');
    }

    if (filterNick === 'attached') {
        list = list.filter(p => Boolean(p.tiktok_username && p.tiktok_username.trim()));
    } else if (filterNick === 'unattached') {
        list = list.filter(p => !Boolean(p.tiktok_username && p.tiktok_username.trim()));
    }

    if (keyword) {
        list = list.filter(p => {
            const name = (p.name || '').toLowerCase();
            const u = (p.tiktok_username || '').toLowerCase();
            const proxy = (p.raw_proxy || '').toLowerCase();
            const gid = (p.gpm_id || '').toLowerCase();
            const nstat = (p.notify_status || 'tracking').toLowerCase();
            return name.includes(keyword) || u.includes(keyword) || proxy.includes(keyword) || gid.includes(keyword) || nstat.includes(keyword);
        });
    }

    list.sort((a, b) => {
        let res = 0;
        if (gpmSortField === 'followers_count') {
            res = (a.followers_count || 0) - (b.followers_count || 0);
        } else if (gpmSortField === 'name') {
            res = (a.name || '').localeCompare(b.name || '', 'vi', { sensitivity: 'base' });
        } else if (gpmSortField === 'tiktok_username') {
            res = (a.tiktok_username || '').localeCompare(b.tiktok_username || '', 'vi', { sensitivity: 'base' });
        } else if (gpmSortField === 'eligible_10k') {
            const ea = (a.eligible_10k || (a.followers_count || 0) >= 10000) ? 1 : 0;
            const eb = (b.eligible_10k || (b.followers_count || 0) >= 10000) ? 1 : 0;
            res = ea - eb;
        } else if (gpmSortField === 'notify_status') {
            res = (a.notify_status || 'tracking').localeCompare(b.notify_status || 'tracking');
        } else if (gpmSortField === 'last_checked') {
            res = (a.last_checked || '').localeCompare(b.last_checked || '');
        }
        return gpmSortDirection === 'asc' ? res : -res;
    });

    const header = ['Tên Profile GPM', 'GPM ID', 'TikTok Username', 'Proxy', 'Số Follower', 'Chuẩn 10K Beta', 'Trạng Thái Theo Dõi', 'Lần Quét Cuối'];
    const rows = [header, ...list.map(p => {
        const ns = (p.notify_status || 'tracking').toLowerCase();
        const nsLabel = ns === 'sent' ? 'Đã gửi' : (ns === 'muted' ? 'Bỏ theo dõi' : 'Đang theo dõi');
        return [
            p.name || '',
            p.gpm_id || '',
            p.tiktok_username || '',
            p.raw_proxy || '',
            p.followers_count || 0,
            (p.eligible_10k || (p.followers_count || 0) >= 10000) ? 'Đạt' : 'Chưa Đạt',
            nsLabel,
            p.last_checked || ''
        ];
    })];

    const dateStr = new Date().toISOString().slice(0, 10);
    downloadCsv(`dan_tai_khoan_gpm_${dateStr}.csv`, rows);
}

function renderGpmProfilesTable() {
    const tbody = document.getElementById('gpmTableBody');
    const eligibleGrid = document.getElementById('eligibleCardsGrid');
    if (!tbody) return;

    const filter10k = document.getElementById('filterGpm10k') ? document.getElementById('filterGpm10k').value : 'all';
    const filterNotify = document.getElementById('filterGpmNotify') ? document.getElementById('filterGpmNotify').value : 'all';
    const filterNick = document.getElementById('filterGpmNick') ? document.getElementById('filterGpmNick').value : 'all';
    const keyword = (document.getElementById('searchGpmKeyword') ? document.getElementById('searchGpmKeyword').value : '').trim().toLowerCase();

    let list = (cachedGpmProfiles || []).slice();

    // 1. Lọc theo chuẩn 10K
    if (filter10k === '10k') {
        list = list.filter(p => Boolean(p.eligible_10k === 1 || (p.followers_count || 0) >= 10000));
    } else if (filter10k === 'growing') {
        list = list.filter(p => !Boolean(p.eligible_10k === 1 || (p.followers_count || 0) >= 10000));
    }

    // 2. Lọc theo trạng thái theo dõi 10K
    if (filterNotify === 'tracking') {
        list = list.filter(p => (p.notify_status || 'tracking').toLowerCase() === 'tracking');
    } else if (filterNotify === 'sent') {
        list = list.filter(p => (p.notify_status || '').toLowerCase() === 'sent');
    } else if (filterNotify === 'muted') {
        list = list.filter(p => (p.notify_status || '').toLowerCase() === 'muted');
    }

    // 3. Lọc theo trạng thái gán nick
    if (filterNick === 'attached') {
        list = list.filter(p => Boolean(p.tiktok_username && p.tiktok_username.trim()));
    } else if (filterNick === 'unattached') {
        list = list.filter(p => !Boolean(p.tiktok_username && p.tiktok_username.trim()));
    }

    // 4. Lọc từ khóa
    if (keyword) {
        list = list.filter(p => {
            const name = (p.name || '').toLowerCase();
            const u = (p.tiktok_username || '').toLowerCase();
            const proxy = (p.raw_proxy || '').toLowerCase();
            const gid = (p.gpm_id || '').toLowerCase();
            const nstat = (p.notify_status || 'tracking').toLowerCase();
            return name.includes(keyword) || u.includes(keyword) || proxy.includes(keyword) || gid.includes(keyword) || nstat.includes(keyword);
        });
    }

    // 5. Sắp xếp
    list.sort((a, b) => {
        let res = 0;
        if (gpmSortField === 'followers_count') {
            res = (a.followers_count || 0) - (b.followers_count || 0);
        } else if (gpmSortField === 'name') {
            res = (a.name || '').localeCompare(b.name || '', 'vi', { sensitivity: 'base' });
        } else if (gpmSortField === 'tiktok_username') {
            res = (a.tiktok_username || '').localeCompare(b.tiktok_username || '', 'vi', { sensitivity: 'base' });
        } else if (gpmSortField === 'eligible_10k') {
            const ea = (a.eligible_10k || (a.followers_count || 0) >= 10000) ? 1 : 0;
            const eb = (b.eligible_10k || (b.followers_count || 0) >= 10000) ? 1 : 0;
            res = ea - eb;
        } else if (gpmSortField === 'notify_status') {
            res = (a.notify_status || 'tracking').localeCompare(b.notify_status || 'tracking');
        } else if (gpmSortField === 'last_checked') {
            res = (a.last_checked || '').localeCompare(b.last_checked || '');
        }
        return gpmSortDirection === 'asc' ? res : -res;
    });

    // Cập nhật badge số lượng
    const badgeCount = document.getElementById('badgeGpmCount');
    if (badgeCount) {
        badgeCount.textContent = `${list.length}/${cachedGpmProfiles.length} Profile`;
    }

    // Cập nhật icon sort trên header
    ['name', 'tiktok_username', 'followers_count', 'eligible_10k', 'notify_status'].forEach(f => {
        const th = document.getElementById(`th-gpm-${f}`);
        if (!th) return;
        const icon = th.querySelector('.sort-icon');
        if (!icon) return;
        if (gpmSortField === f) {
            th.classList.add('sorted');
            icon.className = gpmSortDirection === 'asc' ? 'fa-solid fa-sort-up sort-icon active' : 'fa-solid fa-sort-down sort-icon active';
        } else {
            th.classList.remove('sorted');
            icon.className = 'fa-solid fa-sort sort-icon';
        }
    });

    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-muted"><i class="fa-solid fa-folder-open" style="font-size: 24px; opacity: 0.3; display: block; margin-bottom: 8px;"></i>Không tìm thấy profile nào phù hợp với bộ lọc.</td></tr>`;
    } else {
        tbody.innerHTML = list.map(p => {
            const hasUsername = Boolean(p.tiktok_username && p.tiktok_username.trim());
            const usernameDisplay = hasUsername
                ? `<div style="display:flex; align-items:center; gap:6px; min-width:0;">
                    <a href="https://www.tiktok.com/@${escapeHtml(p.tiktok_username)}" target="_blank" class="table-text-truncate" style="max-width:150px; color:var(--accent-cyan); font-weight:700; text-decoration:none; display:inline-flex; align-items:center; gap:4px;" title="@${escapeHtml(p.tiktok_username)}">
                        <i class="fa-brands fa-tiktok" style="flex-shrink:0;"></i> <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">@${escapeHtml(p.tiktok_username)}</span>
                    </a>
                    <button type="button" class="btn-inline-edit has-tooltip tooltip-top" onclick="openEditUsernameModal('${escapeHtml(p.gpm_id)}', '${escapeHtml(p.name)}', '${escapeHtml(p.tiktok_username || '')}', ${p.followers_count || 0})" data-tooltip="Sửa Nick TikTok & Chỉ Số">
                        <i class="fa-solid fa-pen"></i>
                    </button>
                   </div>`
                : `<div style="display:flex; align-items:center; gap:6px;">
                    <span class="text-muted" style="font-size:12px;"><i class="fa-brands fa-tiktok"></i> Chưa gắn</span>
                    <button type="button" class="btn-inline-edit has-tooltip tooltip-top" onclick="openEditUsernameModal('${escapeHtml(p.gpm_id)}', '${escapeHtml(p.name)}', '', ${p.followers_count || 0})" data-tooltip="Gán Nick TikTok Cho Profile" style="width:auto; padding:0 8px; font-size:10.5px; gap:4px;">
                        <i class="fa-solid fa-plus"></i> Gán
                    </button>
                   </div>`;

            const followersCount = p.followers_count || 0;
            const is10k = Boolean(p.eligible_10k || followersCount >= 10000);
            const followersDisplay = `
                <div>
                    <strong style="font-size:14.5px; color:${is10k ? 'var(--accent-gold)' : 'var(--accent-cyan)'};">
                        ${followersCount.toLocaleString()}
                    </strong>
                    ${p.last_checked ? `<div style="font-size:10.5px; color:var(--text-muted); margin-top:2px;"><i class="fa-regular fa-clock"></i> ${escapeHtml(p.last_checked.slice(5, 16))}</div>` : ''}
                </div>
            `;

            const nStatus = (p.notify_status || 'tracking').toLowerCase();
            let notifyBadge = '';
            if (nStatus === 'sent') {
                notifyBadge = `<span class="badge badge-sent badge-interactive has-tooltip tooltip-top" onclick="cycleProfileNotifyStatus('${escapeHtml(p.gpm_id)}', '${nStatus}')" data-tooltip="Đã gửi Telegram khi đạt 10K (Bấm để đổi trạng thái)"><i class="fa-solid fa-circle-check"></i> Đã gửi</span>`;
            } else if (nStatus === 'muted') {
                notifyBadge = `<span class="badge badge-muted badge-interactive has-tooltip tooltip-top" onclick="cycleProfileNotifyStatus('${escapeHtml(p.gpm_id)}', '${nStatus}')" data-tooltip="Bỏ theo dõi (không gửi Telegram). Bấm để theo dõi"><i class="fa-solid fa-bell-slash"></i> Bỏ theo dõi</span>`;
            } else {
                notifyBadge = `<span class="badge badge-tracking badge-interactive has-tooltip tooltip-top" onclick="cycleProfileNotifyStatus('${escapeHtml(p.gpm_id)}', '${nStatus}')" data-tooltip="Đang theo dõi (gửi Telegram khi &ge; 10K). Bấm để bỏ theo dõi"><i class="fa-solid fa-bell"></i> Đang theo dõi</span>`;
            }

            return `
            <tr>
                <td>
                    <div class="table-text-truncate" style="max-width: 175px;" title="${escapeHtml(p.name)}">
                        <strong>${escapeHtml(p.name)}</strong>
                    </div>
                </td>
                <td>
                    <div class="table-text-truncate" style="max-width: 170px;" title="${escapeHtml(p.raw_proxy || 'Direct IP')}">
                        <code>${escapeHtml(p.raw_proxy || 'Direct IP')}</code>
                    </div>
                </td>
                <td>${usernameDisplay}</td>
                <td>${followersDisplay}</td>
                <td>
                    ${(() => {
                    const pStatus = (p.status || 'active').toLowerCase();
                    const pReason = p.status_reason ? escapeHtml(p.status_reason) : '';
                    if (pStatus === 'banned') {
                        return `<span class="badge badge-banned has-tooltip tooltip-top" data-tooltip="${pReason || 'Tài khoản bị cấm vĩnh viễn'}"><i class="fa-solid fa-ban"></i> BANNED</span>`;
                    } else if (pStatus === 'restricted') {
                        return `<span class="badge badge-restricted has-tooltip tooltip-top" data-tooltip="${pReason || 'Tài khoản bị hạn chế đăng bài'}"><i class="fa-solid fa-triangle-exclamation"></i> HẠN CHẾ</span>`;
                    } else if (pStatus === 'checkpoint') {
                        return `<span class="badge badge-checkpoint has-tooltip tooltip-top" data-tooltip="${pReason || 'Yêu cầu giải Captcha'}"><i class="fa-solid fa-puzzle-piece"></i> CAPTCHA</span>`;
                    } else if (pStatus === 'unlogged') {
                        return `<span class="badge badge-unlogged has-tooltip tooltip-top" data-tooltip="${pReason || 'Chưa đăng nhập / hết phiên'}"><i class="fa-solid fa-right-to-bracket"></i> HẾT PHIÊN</span>`;
                    } else if (pStatus === 'proxy_dead') {
                        return `<span class="badge badge-proxy-dead has-tooltip tooltip-top" data-tooltip="${pReason || 'Proxy chết / lỗi kết nối'}"><i class="fa-solid fa-network-wired"></i> PROXY LỖI</span>`;
                    } else if (is10k) {
                        return '<span class="badge badge-success"><i class="fa-solid fa-trophy"></i> ĐỦ 10K BETA!</span>';
                    } else {
                        return '<span class="badge badge-info"><i class="fa-solid fa-seedling"></i> Đang Nuôi</span>';
                    }
                })()}
                </td>
                <td>${notifyBadge}</td>
                <td style="text-align: center;">
                    <div class="action-dropdown-wrap">
                        <button type="button" class="btn-more-actions" id="btn-more-gpm-${escapeHtml(p.gpm_id)}" 
                            onclick="toggleActionMenu(event, 'gpm-${escapeHtml(p.gpm_id)}')" 
                            title="Tùy chọn thao tác">
                            <i class="fa-solid fa-ellipsis"></i>
                        </button>
                        <div class="action-dropdown-menu" id="action-menu-gpm-${escapeHtml(p.gpm_id)}">
                            <button type="button" class="action-dropdown-item" onclick="scanSingleProfileFollowers('${escapeHtml(p.gpm_id)}', this); closeAllActionMenus();">
                                <i class="fa-solid fa-magnifying-glass-chart" style="color:var(--accent-pink);"></i> Quét Follower ngay
                            </button>
                            <button type="button" class="action-dropdown-item" onclick="openEditUsernameModal('${escapeHtml(p.gpm_id)}', '${escapeHtml(p.name)}', '${escapeHtml(p.tiktok_username || '')}', ${followersCount}); closeAllActionMenus();">
                                <i class="fa-solid fa-pen-to-square" style="color:var(--accent-cyan);"></i> Sửa Nick & Chỉ số
                            </button>
                            ${nStatus === 'tracking' ? `
                            <button type="button" class="action-dropdown-item" onclick="setProfileNotifyStatus('${escapeHtml(p.gpm_id)}', 'muted'); closeAllActionMenus();">
                                <i class="fa-solid fa-bell-slash" style="color:#94a3b8;"></i> Bỏ theo dõi (Mute 10K)
                            </button>
                            <button type="button" class="action-dropdown-item" onclick="setProfileNotifyStatus('${escapeHtml(p.gpm_id)}', 'sent'); closeAllActionMenus();">
                                <i class="fa-solid fa-circle-check" style="color:#60a5fa;"></i> Đánh dấu đã gửi
                            </button>` : nStatus === 'sent' ? `
                            <button type="button" class="action-dropdown-item" onclick="setProfileNotifyStatus('${escapeHtml(p.gpm_id)}', 'tracking'); closeAllActionMenus();">
                                <i class="fa-solid fa-rotate-right" style="color:#fbbf24;"></i> Theo dõi lại (tiếp tục theo dõi)
                            </button>
                            <button type="button" class="action-dropdown-item" onclick="setProfileNotifyStatus('${escapeHtml(p.gpm_id)}', 'muted'); closeAllActionMenus();">
                                <i class="fa-solid fa-bell-slash" style="color:#94a3b8;"></i> Bỏ theo dõi (Mute 10K)
                            </button>` : `
                            <button type="button" class="action-dropdown-item" onclick="setProfileNotifyStatus('${escapeHtml(p.gpm_id)}', 'tracking'); closeAllActionMenus();">
                                <i class="fa-solid fa-bell" style="color:#34d399;"></i> Theo dõi (gửi khi đủ 10K)
                            </button>`}
                            ${hasUsername ? `
                            <a href="https://www.tiktok.com/@${escapeHtml(p.tiktok_username)}" target="_blank" rel="noopener" class="action-dropdown-item" onclick="closeAllActionMenus()">
                                <i class="fa-brands fa-tiktok" style="color:#00f2fe;"></i> Mở kênh TikTok
                            </a>` : ''}
                            <button type="button" class="action-dropdown-item" onclick="copyTextToClipboard('${escapeHtml(hasUsername ? p.tiktok_username : p.gpm_id)}', 'Đã sao chép!'); closeAllActionMenus();">
                                <i class="fa-solid fa-copy" style="color:#94a3b8;"></i> Sao chép ${hasUsername ? 'Username' : 'GPM ID'}
                            </button>
                            <div class="dropdown-divider"></div>
                            <button type="button" class="action-dropdown-item text-danger" onclick="deleteGpmProfileFromList('${escapeHtml(p.gpm_id)}', '${escapeHtml(p.name)}'); closeAllActionMenus();">
                                <i class="fa-solid fa-trash text-danger"></i> Xóa Kênh / Profile
                            </button>
                        </div>
                    </div>
                </td>
            </tr>
            `;
        }).join('');
    }

    // Cập nhật tab 10k follower
    if (eligibleGrid) {
        const eligibleList = (cachedGpmProfiles || []).filter(p => p.eligible_10k === 1 || (p.followers_count || 0) >= 10000);
        if (eligibleList.length > 0) {
            eligibleGrid.innerHTML = eligibleList.map(e => `
                <div class="glass-panel" style="border-color: rgba(245, 158, 11, 0.4); background: linear-gradient(135deg, rgba(245, 158, 11, 0.1), rgba(20, 26, 40, 0.9));">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h4 style="color:var(--accent-gold); font-size:16px;">
                            <i class="fa-solid fa-trophy"></i> @${escapeHtml(e.tiktok_username || e.name)}
                        </h4>
                        <span class="badge badge-success">Sẵn Sàng Bật Kiếm Tiền</span>
                    </div>
                    <div style="margin-top:12px; font-size:13px; color:var(--text-secondary);">
                        <p><strong>Followers:</strong> <span style="color:white; font-size:16px; font-weight:700;">${(e.followers_count || 0).toLocaleString()}</span></p>
                        <p><strong>Profile GPM:</strong> ${escapeHtml(e.name)}</p>
                        <p><strong>Proxy:</strong> ${escapeHtml(e.raw_proxy || 'Direct')}</p>
                        ${e.last_checked ? `<p><strong>Lần quét gần nhất:</strong> ${escapeHtml(e.last_checked)}</p>` : ''}
                    </div>
                </div>
            `).join('');
        } else {
            eligibleGrid.innerHTML = `
                <div class="card-empty-state">
                    <i class="fa-solid fa-chart-line"></i>
                    <p>Hệ thống đang theo dõi tăng trưởng các tài khoản TikTok. Khi có tài khoản đạt mốc 10.000 Followers (đủ điều kiện tham gia TikTok Creator Rewards), thông tin tài khoản sẽ hiển thị tại đây và hệ thống sẽ tự động gửi thông báo qua Telegram.</p>
                </div>
            `;
        }
    }
}

async function setProfileNotifyStatus(gpmId, newStatus) {
    try {
        const res = await fetch(`/api/profiles/${encodeURIComponent(gpmId)}/notify-status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            if (cachedGpmProfiles) {
                const target = cachedGpmProfiles.find(p => p.gpm_id === gpmId);
                if (target) {
                    target.notify_status = newStatus;
                }
            }
            showToast(`✅ Đã chuyển trạng thái theo dõi: ${data.label || newStatus}`);
            renderGpmProfilesTable();
        } else {
            showToast(data.detail || data.message || 'Lỗi cập nhật trạng thái theo dõi', true);
        }
    } catch (err) {
        console.error('Lỗi setProfileNotifyStatus:', err);
        showToast('Lỗi kết nối khi cập nhật trạng thái theo dõi: ' + err.message, true);
    }
}

function cycleProfileNotifyStatus(gpmId, currentStatus) {
    const cur = (currentStatus || 'tracking').toLowerCase();
    let nextStatus = 'tracking';
    if (cur === 'tracking') {
        nextStatus = 'muted';
    } else if (cur === 'muted') {
        nextStatus = 'tracking';
    } else if (cur === 'sent') {
        nextStatus = 'tracking';
    }
    setProfileNotifyStatus(gpmId, nextStatus);
}

async function deleteGpmProfileFromList(gpmId, profileName) {
    closeAllActionMenus();
    const ok = await showConfirmDialog({
        title: 'Xóa Profile GPMLogin',
        message: `Bạn có chắc chắn muốn XÓA profile "${profileName}" khỏi hệ thống Quản lý Farm?`,
        details: 'Hệ thống sẽ ngừng theo dõi và quản lý profile này.',
        confirmText: 'Xóa Profile',
        confirmClass: 'btn-danger'
    });
    if (!ok) return;
    try {
        const res = await fetch(`/api/gpm/profiles/${gpmId}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(`✅ ${data.message || 'Đã xóa profile thành công!'}`);
            loadGpmProfiles();
            loadDashboardStats();
        } else {
            showToast(data.message || 'Không thể xóa profile', true);
        }
    } catch (err) {
        showToast('Lỗi khi xóa profile: ' + err.message, true);
    }
}

// Quét follower 1 profile cụ thể
async function scanSingleProfileFollowers(gpmId, btn) {
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Quét...';
    }
    showToast('Đang kết nối GPMLogin và trích xuất số follower TikTok...');
    try {
        const res = await fetch(`/api/profiles/${gpmId}/scan`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            const fStr = (data.followers || 0).toLocaleString();
            showToast(`✅ Quét thành công: @${data.username || 'N/A'} đạt ${fStr} followers!`);
            loadGpmProfiles();
            loadDashboardStats();
            return data;
        } else {
            showToast(data.message || 'Lỗi quét profile', true);
            return data;
        }
    } catch (err) {
        showToast('Không thể quét follower: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// Quét follower toàn bộ nick tuần tự với Live Progress & Nút Dừng
let _scanProgressPoller = null;
let _lastScanProgressIndex = 0;

async function checkScanProgress() {
    try {
        const res = await fetch('/api/profiles/scan-progress');
        const data = await res.json();
        const container = document.getElementById('scanProgressBarContainer');
        const titleEl = document.getElementById('scanProgressTitle');
        const subEl = document.getElementById('scanProgressSubtitle');
        const pctEl = document.getElementById('scanProgressPercent');
        const fillEl = document.getElementById('scanProgressBarFill');
        const scanBtn = document.getElementById('btnScanAllFollowersTab');

        if (!container) return;

        if (data.is_scanning) {
            container.style.display = 'block';
            if (scanBtn) {
                scanBtn.disabled = true;
                scanBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Quét...';
            }

            const total = data.total || 0;
            const current = data.current !== undefined ? data.current : (data.current_index !== undefined ? data.current_index : 0);
            const pct = data.percent !== undefined ? data.percent : (total > 0 ? Math.round((current / total) * 100) : 0);

            if (titleEl) {
                if (data.current_profile_name) {
                    titleEl.innerHTML = `Đang quét: <span style="color:var(--accent-cyan); font-weight:700;">${escapeHtml(data.current_profile_name)}</span> [${current}/${total}]`;
                } else {
                    titleEl.textContent = `Đang quét Follower [${current}/${total}]...`;
                }
            }
            if (subEl) {
                subEl.textContent = data.status_message || data.message || 'Chế độ ZeroRAM siêu nhẹ, tự động giải phóng bộ nhớ sau mỗi nick';
            }
            if (pctEl) pctEl.textContent = `${pct}%`;
            if (fillEl) fillEl.style.width = `${pct}%`;

            // Cập nhật bảng dữ liệu khi nick vừa quét xong
            if (current > _lastScanProgressIndex) {
                _lastScanProgressIndex = current;
                loadGpmProfiles();
                loadDashboardStats();
            }
        } else {
            // Không quét hoặc đã kết thúc
            if (_scanProgressPoller) {
                clearInterval(_scanProgressPoller);
                _scanProgressPoller = null;
            }
            _lastScanProgressIndex = 0;

            if (container.style.display !== 'none') {
                if (fillEl) fillEl.style.width = '100%';
                if (pctEl) pctEl.textContent = '100%';
                if (titleEl) titleEl.textContent = data.status_message || data.message || 'Đã hoàn thành quét Follower!';
                setTimeout(() => {
                    container.style.display = 'none';
                    if (fillEl) fillEl.style.width = '0%';
                }, 2500);
            }

            if (scanBtn) {
                scanBtn.disabled = false;
                scanBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass-chart"></i> Quét Follower Tất Cả Nick';
            }

            loadGpmProfiles();
            loadDashboardStats();
        }
    } catch (err) {
        console.error('Lỗi kiểm tra tiến độ quét:', err);
    }
}

function startScanProgressPolling() {
    if (_scanProgressPoller) clearInterval(_scanProgressPoller);
    _lastScanProgressIndex = 0;
    checkScanProgress();
    _scanProgressPoller = setInterval(checkScanProgress, 800);
}

async function stopAllProfilesScan(btn) {
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Dừng...';
    }
    showToast('🛑 Đang yêu cầu dừng quét... Nick hiện tại sẽ được đóng ngay lập tức.');
    try {
        const res = await fetch('/api/profiles/scan-stop', { method: 'POST' });
        const data = await res.json();
        showToast(data.message || 'Đã gửi lệnh dừng tiến trình quét thành công!');
        setTimeout(checkScanProgress, 500);
    } catch (err) {
        showToast('Lỗi khi dừng quét: ' + err.message, true);
    } finally {
        setTimeout(() => {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = origHtml;
            }
        }, 1500);
    }
}

async function scanAllProfilesFollowers(btn) {
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Khởi Động...';
    }
    showToast('🚀 Bắt đầu quét Follower cho toàn bộ nick GPMLogin (Chế độ Low-RAM)...');
    try {
        const res = await fetch('/api/profiles/scan-all', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'warning') {
            showToast(data.message, true);
        } else {
            showToast('Tiến trình quét đang chạy ngầm, bạn có thể theo dõi tiến độ hoặc bấm Dừng Quét bất kỳ lúc nào!');
        }
        startScanProgressPolling();
    } catch (err) {
        showToast('Lỗi khi kích hoạt quét tất cả: ' + err.message, true);
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// Quản lý Modal sửa Nick & Followers
function openEditUsernameModal(gpmId, profileName, currentUsername, followers) {
    document.getElementById('editProfileGpmId').value = gpmId;
    document.getElementById('editProfileName').value = profileName || gpmId;
    document.getElementById('editProfileUsername').value = (currentUsername || '').replace(/^@/, '');
    document.getElementById('editProfileFollowers').value = followers || 0;
    const modal = document.getElementById('editProfileUsernameModal');
    if (modal) modal.classList.add('active');
}

function closeEditUsernameModal() {
    const modal = document.getElementById('editProfileUsernameModal');
    if (modal) modal.classList.remove('active');
}

async function saveProfileUsernameFromModal(btn) {
    const gpmId = document.getElementById('editProfileGpmId').value;
    const usernameInput = document.getElementById('editProfileUsername');
    const followersInput = document.getElementById('editProfileFollowers');
    const username = usernameInput ? usernameInput.value.trim().replace(/^@/, '') : '';
    const rawFollowers = followersInput ? followersInput.value.trim() : '0';
    const followers = parseInt(rawFollowers, 10);

    if (!username) {
        markInputError('editProfileUsername', 'Vui lòng nhập Username TikTok (không được để trống)!');
        return;
    }
    if (isNaN(followers) || followers < 0) {
        markInputError('editProfileFollowers', 'Số lượng Followers phải là số nguyên không âm (>= 0)!');
        return;
    }

    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Lưu...';
    }

    try {
        const resU = await fetch(`/api/profiles/${gpmId}/username`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username })
        });
        const dataU = await resU.json();
        if (!resU.ok) {
            showToast('Lỗi cập nhật username: ' + (dataU.detail || dataU.message || 'Thất bại'), 'error');
            return;
        }

        const resS = await fetch('/api/profiles/stats', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                gpm_id: gpmId,
                followers: followers,
                views: 0,
                username: username
            })
        });
        const dataS = await resS.json();
        if (!resS.ok) {
            showToast('Lỗi cập nhật chỉ số: ' + (dataS.detail || dataS.message || 'Thất bại'), 'error');
            return;
        }

        showToast(`✅ Đã lưu thông tin @${username} thành công!`, 'success');
        closeEditUsernameModal();
        loadGpmProfiles();
        loadDashboardStats();
    } catch (err) {
        showToast('Lỗi khi lưu thông tin: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

async function scanCurrentEditProfile(btn) {
    const gpmId = document.getElementById('editProfileGpmId').value;
    if (!gpmId) return;
    const res = await scanSingleProfileFollowers(gpmId, btn);
    if (res && res.success) {
        if (res.username) document.getElementById('editProfileUsername').value = res.username;
        if (res.followers !== undefined) document.getElementById('editProfileFollowers').value = res.followers;
    }
}

async function deleteCurrentEditProfile(btn) {
    const gpmId = document.getElementById('editProfileGpmId').value;
    const name = document.getElementById('editProfileName').value;
    if (!gpmId) return;
    closeEditUsernameModal();
    await deleteGpmProfileFromList(gpmId, name || gpmId);
}

// Quản lý Modal Cài Đặt Lịch Quét Follower Tự Động
async function loadFollowerSchedulerBadge() {
    try {
        const res = await fetch('/api/settings/follower-scheduler');
        const data = await res.json();
        const badge = document.getElementById('badgeFollowerSchedulerState');
        if (!badge) return;

        if (data.enabled) {
            badge.className = 'badge badge-success';
            if (data.mode === 'daily_times') {
                badge.textContent = `Bật (${data.times || '08:00, 20:00'})`;
            } else {
                badge.textContent = `Bật (Mỗi ${data.interval_hours || 6}h)`;
            }
        } else {
            badge.className = 'badge badge-secondary';
            badge.textContent = 'Đang Tắt';
        }
    } catch (err) {
        console.error('Lỗi nạp badge follower scheduler:', err);
    }
}

function toggleFollowerScanModeUI() {
    const isDaily = document.getElementById('scanModeDaily').checked;
    const wrapDaily = document.getElementById('wrapDailyTimes');
    const wrapInterval = document.getElementById('wrapIntervalHours');
    if (wrapDaily) wrapDaily.style.display = isDaily ? 'block' : 'none';
    if (wrapInterval) wrapInterval.style.display = isDaily ? 'none' : 'block';
}

async function openFollowerSchedulerModal() {
    try {
        const res = await fetch('/api/settings/follower-scheduler');
        const data = await res.json();
        document.getElementById('chkFollowerSchedulerEnable').checked = Boolean(data.enabled);
        if (data.mode === 'interval') {
            document.getElementById('scanModeInterval').checked = true;
        } else {
            document.getElementById('scanModeDaily').checked = true;
        }
        if (data.times) document.getElementById('inputFollowerScanTimes').value = data.times;
        if (data.interval_hours) document.getElementById('selectFollowerIntervalHours').value = String(data.interval_hours);
        toggleFollowerScanModeUI();
    } catch (err) {
        console.error('Lỗi đọc settings:', err);
    }

    const modal = document.getElementById('followerSchedulerModal');
    if (modal) modal.classList.add('active');
}

function closeFollowerSchedulerModal() {
    const modal = document.getElementById('followerSchedulerModal');
    if (modal) modal.classList.remove('active');
}

async function saveFollowerSchedulerSettings(btn) {
    const enabled = document.getElementById('chkFollowerSchedulerEnable').checked;
    const isDaily = document.getElementById('scanModeDaily').checked;
    const mode = isDaily ? 'daily_times' : 'interval';
    const timesInput = document.getElementById('inputFollowerScanTimes');
    const intervalSelect = document.getElementById('selectFollowerIntervalHours');
    const times = timesInput ? timesInput.value.trim() : '';
    const interval_hours = intervalSelect ? (parseInt(intervalSelect.value, 10) || 6) : 6;

    if (mode === 'daily_times') {
        if (!times) {
            markInputError('inputFollowerScanTimes', 'Vui lòng nhập khung giờ quét (Ví dụ: 08:00, 20:00)!');
            return;
        }
        const timeSlots = times.split(',').map(s => s.trim()).filter(Boolean);
        const badSlot = timeSlots.find(s => !isValidTimeHHMM(s));
        if (badSlot || timeSlots.length === 0) {
            markInputError('inputFollowerScanTimes', `Khung giờ "${badSlot || 'trống'}" không hợp lệ! Định dạng chuẩn: HH:MM (00:00 - 23:59)`);
            return;
        }
    } else {
        if (isNaN(interval_hours) || interval_hours < 1 || interval_hours > 48) {
            markInputError('selectFollowerIntervalHours', 'Chu kỳ quét lặp lại phải từ 1 đến 48 giờ!');
            return;
        }
    }

    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Lưu...';
    }

    try {
        const res = await fetch('/api/settings/follower-scheduler', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                enabled: enabled,
                mode: mode,
                times: times,
                interval_hours: interval_hours
            })
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast('✅ Đã lưu cấu hình lịch quét Follower thành công!', 'success');
            closeFollowerSchedulerModal();
            loadFollowerSchedulerBadge();
        } else {
            showToast('Lỗi lưu cấu hình: ' + (data.detail || data.message || 'Thất bại'), 'error');
        }
    } catch (err) {
        showToast('Lỗi gửi cài đặt: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// 5. Upload Modal
function openUploadModal(videoId) {
    const video = cachedVideos.find(v => v.id == videoId);
    if (!video || !video.rendered_path) {
        showToast('Video chưa được render AI!', 'warning');
        return;
    }

    const select = document.getElementById('modalProfileSelect');
    if (cachedGpmProfiles.length === 0) {
        showToast('Vui lòng đồng bộ danh sách GPMLogin trước!', 'warning');
        return;
    }

    select.innerHTML = cachedGpmProfiles.map(p => `
        <option value="${p.gpm_id}">${escapeHtml(p.name)} (${p.raw_proxy || 'No Proxy'})</option>
    `).join('');

    document.getElementById('modalVideoPath').value = video.rendered_path;
    document.getElementById('modalVideoTitle').value = video.ai_title || video.title;
    document.getElementById('uploadModal').classList.add('active');
}

function closeUploadModal() {
    document.getElementById('uploadModal').classList.remove('active');
}

async function executeUploadVideo() {
    const profileId = document.getElementById('modalProfileSelect')?.value;
    const videoPath = (document.getElementById('modalVideoPath')?.value || '').trim();
    const title = (document.getElementById('modalVideoTitle')?.value || '').trim();
    const tags = document.getElementById('modalVideoTags')?.value || '';

    if (!profileId) {
        markInputError('modalProfileSelect', 'Vui lòng chọn Profile GPMLogin để đăng video!');
        return;
    }
    if (!videoPath) {
        markInputError('modalVideoPath', 'Đường dẫn video không được để trống!');
        return;
    }
    if (!title) {
        markInputError('modalVideoTitle', 'Vui lòng nhập tiêu đề cho video TikTok!');
        return;
    }

    const btn = document.getElementById('btnConfirmUpload');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang mở GPM & Upload...';

    try {
        const res = await fetch('/api/tiktok/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                gpm_profile_id: profileId,
                video_path: videoPath,
                title: title,
                tags: tags
            })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast('✅ Đã thực hiện xong lệnh đăng video lên TikTok!', 'success');
            closeUploadModal();
        } else {
            showToast('Lỗi: ' + (data.detail || data.message || 'Không thể đăng video'), 'error');
        }
    } catch (err) {
        showToast('Lỗi kết nối upload: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Bắt Đầu Đăng Bài';
    }
}

// 6. Test Telegram Alert (Gửi cảnh báo 10K tới tất cả các kênh đang Bật)
async function testTelegramAlert(btn) {
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Gửi...';
    }
    showToast('Đang gửi tin nhắn cảnh báo thử nghiệm tới các kênh Telegram...');
    try {
        const res = await fetch('/api/telegram/test-alert', { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`✅ ${data.message || 'Đã gửi test alert thành công!'}`, 'success');
        } else {
            showToast('⚠️ ' + (data.message || 'Lỗi gửi test alert'), true);
        }
    } catch (err) {
        showToast('Lỗi gửi Telegram: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// Gửi Báo Cáo Hoạt Động Hàng Ngày Ngay Lập Tức
async function testDailyReportNow(btn) {
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Gửi...';
    }
    showToast('Đang tạo và gửi Báo cáo hoạt động ngày tới các kênh Telegram...');
    try {
        const res = await fetch('/api/telegram/send-daily-report', { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`✅ ${data.message || 'Đã gửi Báo cáo hoạt động ngày thành công!'}`, 'success');
        } else {
            showToast('⚠️ ' + (data.message || 'Lỗi gửi báo cáo ngày'), true);
        }
    } catch (err) {
        showToast('Lỗi gửi Telegram: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// Gửi Cảnh Báo Sự Cố Thử Nghiệm Kèm Hướng Dẫn Khắc Phục
async function testIssueAlertNow(btn) {
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Gửi...';
    }
    showToast('Đang gửi cảnh báo lỗi kèm cách khắc phục thử nghiệm...');
    try {
        const res = await fetch('/api/telegram/test-issue-alert', { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`✅ ${data.message || 'Đã gửi cảnh báo lỗi thành công!'}`, 'success');
        } else {
            showToast('⚠️ ' + (data.message || 'Lỗi gửi cảnh báo lỗi'), true);
        }
    } catch (err) {
        showToast('Lỗi gửi Telegram: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// Bắn cảnh báo sự cố từ System Diagnostics qua Telegram
async function sendDiagnosticsIssueAlertToTelegram(btn) {
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang gửi...';
    }
    try {
        const res = await fetch('/api/system/diagnostics');
        const diag = await res.json();
        const actionItems = diag.action_items || [];
        if (actionItems.length === 0) {
            showToast('🎉 Hệ thống hoạt động hoàn hảo! Không có sự cố nào để cảnh báo.', 'success');
            return;
        }

        const firstErr = actionItems.find(i => i.type === 'error') || actionItems[0];
        const payload = {
            title: `Sự cố phát hiện từ Chẩn Đoán Hệ Thống: ${firstErr.title || firstErr.category}`,
            message: firstErr.message || 'Phát hiện sự cố phần mềm phụ thuộc hoặc cấu hình môi trường.',
            solution: firstErr.message || 'Xem chi tiết hướng dẫn sửa trong tab Chẩn Đoán Hệ Thống.',
            severity: firstErr.type === 'error' ? 'HIGH' : 'WARNING',
            details: `Danh mục: ${firstErr.category || 'Môi trường'} | Tổng số lưu ý: ${actionItems.length}`
        };

        const postRes = await fetch('/api/telegram/send-issue-alert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const postData = await postRes.json();
        if (postRes.ok && postData.status === 'success') {
            showToast('✅ Đã bắn cảnh báo lỗi chẩn đoán qua Telegram thành công!', 'success');
        } else {
            showToast('⚠️ ' + (postData.message || 'Không thể gửi cảnh báo Telegram'), true);
        }
    } catch (err) {
        showToast('Lỗi gửi Telegram: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// Utility
function escapeHtml(text) {
    if (!text) return '';
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return text.toString().replace(/[&<>"']/g, m => map[m]);
}

// ==========================================
// 7. SAVED CHANNELS MANAGER & SETTINGS
// ==========================================
let cachedSavedChannels = [];
let activeModalChannel = null;

async function loadSavedChannels(btn) {
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang tải...';
    }

    try {
        const res = await fetch('/api/youtube/channels');
        const channels = await res.json();
        cachedSavedChannels = channels || [];

        const total = cachedSavedChannels.length;
        const activeCount = cachedSavedChannels.filter(c => c.is_active === 1).length;
        const totalDownloaded = cachedSavedChannels.reduce((sum, c) => sum + (c.downloaded_count || 0), 0);
        const totalRendered = cachedSavedChannels.reduce((sum, c) => sum + (c.rendered_count || 0), 0);

        const elTotal = document.getElementById('savedCountTotal');
        if (elTotal) elTotal.textContent = total;
        const elActive = document.getElementById('savedCountActive');
        if (elActive) elActive.textContent = activeCount;
        const elDl = document.getElementById('savedCountDownloaded');
        if (elDl) elDl.textContent = totalDownloaded;
        const elRd = document.getElementById('savedCountRendered');
        if (elRd) elRd.textContent = totalRendered;
        const badgeCount = document.getElementById('badgeSavedCount');
        if (badgeCount) badgeCount.textContent = `${total} Kênh Đang Theo Dõi`;

        renderSavedChannelsTable();
    } catch (err) {
        console.error('Lỗi khi tải kênh đã lưu:', err);
        showToast('Lỗi khi tải danh sách kênh đã lưu: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// Saved Channels Sorting & Filtering State
let savedSortField = 'default';
let savedSortDirection = 'asc';
let savedFilterCountry = 'all';
let savedFilterMinViews = 0;
let savedFilterMinSubs = 0;
let savedFilterCadence = 'all';

function handleSavedSortSelectChange(val) {
    savedSortField = val;
    renderSavedChannelsTable();
}

function toggleSavedSortDirection() {
    savedSortDirection = savedSortDirection === 'asc' ? 'desc' : 'asc';
    updateSavedSortDirectionBtn();
    renderSavedChannelsTable();
}

function updateSavedSortDirectionBtn() {
    const icon = document.getElementById('savedSortDirIcon');
    const text = document.getElementById('savedSortDirText');
    if (icon) icon.className = savedSortDirection === 'asc' ? 'fa-solid fa-arrow-down-short-wide' : 'fa-solid fa-arrow-down-wide-short';
    if (text) text.textContent = savedSortDirection === 'asc' ? 'Tăng dần' : 'Giảm dần';
}

function handleSavedHeaderSort(field) {
    if (savedSortField === field) {
        toggleSavedSortDirection();
    } else {
        savedSortField = field;
        savedSortDirection = (field === 'title' || field === 'country') ? 'asc' : 'desc';
        const sel = document.getElementById('savedSortSelect');
        if (sel) sel.value = field;
        updateSavedSortDirectionBtn();
        renderSavedChannelsTable();
    }
}

function handleSavedFilterCountryChange(val) {
    savedFilterCountry = val;
    renderSavedChannelsTable();
}

function handleSavedFilterViewsChange(val) {
    savedFilterMinViews = parseInt(val, 10) || 0;
    renderSavedChannelsTable();
}

function handleSavedFilterSubsChange(val) {
    savedFilterMinSubs = parseInt(val, 10) || 0;
    renderSavedChannelsTable();
}

function handleSavedFilterCadenceChange(val) {
    savedFilterCadence = val;
    renderSavedChannelsTable();
}

function resetSavedFilters() {
    savedSortField = 'default';
    savedSortDirection = 'asc';
    savedFilterCountry = 'all';
    savedFilterMinViews = 0;
    savedFilterMinSubs = 0;
    savedFilterCadence = 'all';

    const selSort = document.getElementById('savedSortSelect');
    if (selSort) selSort.value = 'default';
    const selCountry = document.getElementById('savedFilterCountrySelect');
    if (selCountry) selCountry.value = 'all';
    const selViews = document.getElementById('savedFilterViewsSelect');
    if (selViews) selViews.value = '0';
    const selSubs = document.getElementById('savedFilterSubsSelect');
    if (selSubs) selSubs.value = '0';
    const selCadence = document.getElementById('savedFilterCadenceSelect');
    if (selCadence) selCadence.value = 'all';
    const selStatus = document.getElementById('filterSavedStatus');
    if (selStatus) selStatus.value = 'all';
    const inpKw = document.getElementById('searchSavedKeyword');
    if (inpKw) inpKw.value = '';

    updateSavedSortDirectionBtn();
    renderSavedChannelsTable();
}

function getFilteredSavedChannels() {
    const statusFilter = document.getElementById('filterSavedStatus') ? document.getElementById('filterSavedStatus').value : 'all';
    const keyword = (document.getElementById('searchSavedKeyword') ? document.getElementById('searchSavedKeyword').value : '').trim().toLowerCase();

    let list = cachedSavedChannels.slice();

    // 1. Status Filter
    if (statusFilter === 'active') {
        list = list.filter(c => c.is_active === 1);
    } else if (statusFilter === 'inactive') {
        list = list.filter(c => c.is_active === 0);
    }

    // 2. Country Filter
    if (savedFilterCountry !== 'all') {
        list = list.filter(c => (c.country || 'N/A').toUpperCase() === savedFilterCountry.toUpperCase());
    }

    // 3. Min Views Filter
    if (savedFilterMinViews > 0) {
        list = list.filter(c => (c.avg_views || 0) >= savedFilterMinViews);
    }

    // 4. Min Subs Filter
    if (savedFilterMinSubs > 0) {
        list = list.filter(c => (c.subscriber_count || 0) >= savedFilterMinSubs);
    }

    // 5. Cadence Filter
    if (savedFilterCadence === 'daily') {
        list = list.filter(c => c.upload_cadence_days > 0 && c.upload_cadence_days <= 1.0);
    } else if (savedFilterCadence === 'frequent') {
        list = list.filter(c => c.upload_cadence_days > 0 && c.upload_cadence_days <= 3.0);
    } else if (savedFilterCadence === 'weekly') {
        list = list.filter(c => c.upload_cadence_days > 0 && c.upload_cadence_days <= 7.0);
    }

    // 6. Keyword Filter
    if (keyword) {
        list = list.filter(c => {
            const title = (c.title || '').toLowerCase();
            const displayName = (c.display_name || '').toLowerCase();
            const cid = (c.channel_id || '').toLowerCase();
            const handle = (c.handle || '').toLowerCase();
            const country = (c.country || '').toLowerCase();
            return title.includes(keyword) || displayName.includes(keyword) || cid.includes(keyword) || handle.includes(keyword) || country.includes(keyword);
        });
    }

    // 7. Sort
    if (savedSortField !== 'default') {
        list.sort((a, b) => {
            let res = 0;
            if (savedSortField === 'title') {
                const ta = a.display_name || a.title || '';
                const tb = b.display_name || b.title || '';
                res = ta.localeCompare(tb, 'vi', { sensitivity: 'base' });
            } else if (savedSortField === 'country') {
                res = (a.country || '').localeCompare(b.country || '');
            } else if (savedSortField === 'subscriber_count') {
                res = (a.subscriber_count || 0) - (b.subscriber_count || 0);
            } else if (savedSortField === 'video_count') {
                res = (a.video_count || 0) - (b.video_count || 0);
            } else if (savedSortField === 'avg_views') {
                res = (a.avg_views || 0) - (b.avg_views || 0);
            } else if (savedSortField === 'total_view_count') {
                res = (a.total_view_count || 0) - (b.total_view_count || 0);
            } else if (savedSortField === 'views_per_sub_ratio') {
                res = (a.views_per_sub_ratio || 0) - (b.views_per_sub_ratio || 0);
            } else if (savedSortField === 'days_since_last_upload') {
                const da = a.days_since_last_upload !== undefined && a.days_since_last_upload !== null ? a.days_since_last_upload : 9999;
                const db = b.days_since_last_upload !== undefined && b.days_since_last_upload !== null ? b.days_since_last_upload : 9999;
                res = da - db;
            } else if (savedSortField === 'upload_cadence_days') {
                const ca = a.upload_cadence_days > 0 ? a.upload_cadence_days : 9999;
                const cb = b.upload_cadence_days > 0 ? b.upload_cadence_days : 9999;
                res = ca - cb;
            } else if (savedSortField === 'is_active') {
                res = (a.is_active || 0) - (b.is_active || 0);
            }
            return savedSortDirection === 'asc' ? res : -res;
        });
    }

    return list;
}

function exportSavedChannelsCsv() {
    let list = getFilteredSavedChannels();
    if (!list || !list.length) {
        list = cachedSavedChannels || [];
    }
    if (!list.length) {
        showToast('Không có kênh nào đang giám sát để xuất CSV!', true);
        return;
    }

    const headers = [
        'Channel ID',
        'Tên Hiển Thị (Display Name)',
        'Tên Gốc Kênh',
        'Handle',
        'URL Kênh YouTube',
        'Quốc Gia',
        'Subscribers',
        'Tổng Số Video',
        'Lượt Xem TB',
        'Tổng Lượt Xem Kênh',
        'Viral Ratio',
        'Video Mới Nhất',
        'Số Ngày Kể Từ Video Cuối',
        'Tần Suất Đăng (Ngày/Vid)',
        'Video Đã Tải',
        'Video Đã Render 9:16',
        'Trạng Thái',
        'Tự Động Tải MP4',
        'Tự Động Render AI',
        'Proxy Riêng',
        'Thư Mục Tải',
        'Thư Mục Render'
    ];

    const rows = [headers];
    list.forEach(c => {
        rows.push([
            c.channel_id || '',
            c.display_name || c.title || '',
            c.title || '',
            c.handle || '',
            c.url || (c.channel_id ? `https://www.youtube.com/channel/${c.channel_id}` : ''),
            c.country || 'N/A',
            c.subscriber_count !== undefined && c.subscriber_count !== null ? c.subscriber_count : '',
            c.video_count !== undefined && c.video_count !== null ? c.video_count : '',
            c.avg_views !== undefined && c.avg_views !== null ? c.avg_views : '',
            c.total_view_count !== undefined && c.total_view_count !== null ? c.total_view_count : '',
            c.views_per_sub_ratio !== undefined && c.views_per_sub_ratio !== null ? Number(c.views_per_sub_ratio).toFixed(2) : '',
            c.last_upload_date || '',
            c.days_since_last_upload !== undefined && c.days_since_last_upload !== null ? c.days_since_last_upload : '',
            c.upload_cadence_days || '',
            c.downloaded_count || 0,
            c.rendered_count || 0,
            c.is_active === 1 ? 'Hoạt động' : 'Tạm ngưng',
            c.auto_download === 1 ? 'Bật' : 'Tắt',
            c.auto_render === 1 ? 'Bật' : 'Tắt',
            c.custom_proxy || '',
            c.download_dir || '',
            c.render_dir || ''
        ]);
    });

    const dateStr = new Date().toISOString().split('T')[0];
    downloadCsv(`kenh_youtube_giam_sat_${dateStr}.csv`, rows);
}

function renderSavedChannelsTable() {
    const tbody = document.getElementById('savedChannelsBody');
    if (!tbody) return;

    const list = getFilteredSavedChannels();

    const badgeCount = document.getElementById('badgeSavedCount');
    if (badgeCount) badgeCount.textContent = `${list.length}/${cachedSavedChannels.length} Kênh`;

    // Update Header Sort Icons
    ['title', 'country', 'subscriber_count', 'video_count', 'avg_views', 'views_per_sub_ratio', 'days_since_last_upload', 'upload_cadence_days', 'is_active'].forEach(f => {
        const thMap = {
            'title': 'th-saved-title',
            'country': 'th-saved-country',
            'subscriber_count': 'th-saved-subs',
            'video_count': 'th-saved-videos',
            'avg_views': 'th-saved-avg-views',
            'views_per_sub_ratio': 'th-saved-ratio',
            'days_since_last_upload': 'th-saved-last-upload',
            'upload_cadence_days': 'th-saved-cadence',
            'is_active': 'th-saved-active'
        };
        const th = document.getElementById(thMap[f]);
        if (!th) return;
        const icon = th.querySelector('.sort-icon');
        if (!icon) return;
        if (savedSortField === f) {
            th.classList.add('sorted');
            icon.className = savedSortDirection === 'asc' ? 'fa-solid fa-sort-up sort-icon active' : 'fa-solid fa-sort-down sort-icon active';
        } else {
            th.classList.remove('sorted');
            icon.className = 'fa-solid fa-sort sort-icon';
        }
    });

    if (!list.length) {
        tbody.innerHTML = `<tr><td colspan="12" class="text-center py-4 text-muted"><i class="fa-solid fa-folder-open" style="font-size: 24px; opacity: 0.3; display: block; margin-bottom: 8px;"></i>Không tìm thấy kênh nào phù hợp.</td></tr>`;
        return;
    }

    tbody.innerHTML = list.map(c => {
        const cid = c.channel_id || '';
        const hasDisplayName = c.display_name && c.display_name.trim();
        const displayTitle = hasDisplayName ? escapeHtml(c.display_name) : escapeHtml(c.title || cid);
        const origTitle = hasDisplayName ? `<span class="channel-title-main table-text-truncate" style="opacity:0.75; font-size:11px; max-width:200px;" title="Gốc: ${escapeHtml(c.title)}">Gốc: ${escapeHtml(c.title)}</span>` : '';
        const aliasTag = hasDisplayName ? `<span class="channel-alias-tag"><i class="fa-solid fa-tag"></i> Tên riêng</span>` : '';

        const handleText = c.handle ? `<span class="table-text-truncate" style="max-width:180px; font-size:11px; color:var(--accent-cyan); font-weight:500;" title="@${escapeHtml(c.handle.replace('@', ''))}">@${escapeHtml(c.handle.replace('@', ''))}</span>` : '';
        const chUrl = c.url || (cid ? `https://www.youtube.com/channel/${cid}` : '#');

        const thumbImg = c.thumbnail_url
            ? `<img src="${c.thumbnail_url}" alt="" class="channel-avatar-clickable" onclick="openChannelDetailModal('${escapeHtml(cid)}')" style="width:38px; height:38px; border-radius:50%; object-fit:cover; border:1px solid rgba(255,255,255,0.1); flex-shrink:0;" title="Bấm xem chi tiết kênh">`
            : `<div class="channel-avatar-clickable" onclick="openChannelDetailModal('${escapeHtml(cid)}')" style="width:38px; height:38px; border-radius:50%; background:rgba(255,255,255,0.06); display:flex; align-items:center; justify-content:center; color:var(--text-muted); flex-shrink:0;" title="Bấm xem chi tiết kênh"><i class="fa-brands fa-youtube"></i></div>`;

        const subsFormatted = c.subscriber_count ? formatNumber(c.subscriber_count) : '<span class="text-muted">Ẩn</span>';
        const lastUploadText = c.last_upload_date ? `${c.last_upload_date} (${c.days_since_last_upload || 0} ngày trước)` : 'Chưa có';
        const cadenceDesc = c.upload_cadence_days > 0 ? `${c.upload_cadence_days} ngày/vid` : 'Chưa xác định';

        const dlCount = c.downloaded_count || 0;
        const rdCount = c.rendered_count || 0;

        const isActive = c.is_active === 1;
        const statusBadge = isActive
            ? `<span class="badge badge-success"><i class="fa-solid fa-circle-dot"></i> Hoạt động</span>`
            : `<span class="badge badge-secondary"><i class="fa-solid fa-pause"></i> Tạm ngưng</span>`;

        const ratio = c.views_per_sub_ratio || 0;
        let ratioBadge = '';
        if (ratio > 0) {
            const ratioClass = ratio >= 2.0 ? 'high' : (ratio >= 0.5 ? 'good' : '');
            const fire = ratio >= 1.0 ? '🔥 ' : '';
            ratioBadge = `<div class="badge-ratio ${ratioClass}" title="Tỷ lệ lượt xem trên số người theo dõi">${fire}Ratio: ${ratio.toFixed(2)}x</div>`;
        }

        return `
            <tr data-channel-id="${escapeHtml(cid)}">
                <!-- Col 1: Kênh YouTube (Avatar + Title + Handle + Link) matching Scanner Tab -->
                <td>
                    <div style="display:flex; align-items:flex-start; gap:10px;">
                        ${thumbImg}
                        <div style="display:flex; flex-direction:column; gap:2px; min-width:0;">
                            ${aliasTag}
                            <strong class="channel-title-link" onclick="openChannelDetailModal('${escapeHtml(cid)}')" title="Bấm xem chi tiết kênh: ${displayTitle}">${displayTitle}</strong>
                            ${origTitle}
                            ${handleText}
                            <div style="margin-top:3px;">
                                <a href="${escapeHtml(chUrl)}" target="_blank" rel="noopener" class="channel-link-tag" title="Mở trang YouTube của kênh này">
                                    <i class="fa-solid fa-arrow-up-right-from-square"></i> Mở kênh
                                </a>
                            </div>
                        </div>
                    </div>
                </td>

                <!-- Col 2: Mã Channel ID matching Scanner Tab -->
                <td>
                    <div style="display:flex; align-items:center; gap:4px;">
                        <span class="channel-id-tag" title="${escapeHtml(cid)}">${escapeHtml(cid)}</span>
                        <button type="button" class="btn-copy-id" onclick="copyTextToClipboard('${escapeHtml(cid)}', 'Đã sao chép Channel ID!')" title="Sao chép Channel ID">
                            <i class="fa-solid fa-copy"></i>
                        </button>
                    </div>
                </td>

                <!-- Col 3: Quốc Gia -->
                <td>${getCountryBadge(c.country)}</td>

                <!-- Col 4: Subscribers -->
                <td>
                    <div style="font-weight:700; color:var(--text-primary); font-size:13px;">${subsFormatted}</div>
                </td>

                <!-- Col 5: Tổng Video -->
                <td>
                    <div style="font-size:12.5px; color:#cbd5e1;">${c.video_count ? c.video_count.toLocaleString() : 'N/A'}</div>
                </td>

                <!-- Col 6: Lượt Xem TB -->
                <td>
                    <div style="font-weight:700; color:#fff; font-size:13px;">${c.avg_views ? formatNumber(c.avg_views) : '<span class="text-muted">N/A</span>'}</div>
                </td>

                <!-- Col 7: Tỷ Lệ View/Sub (Separate Column) -->
                <td>
                    ${ratioBadge || '<span class="text-muted" style="font-size:11px;">—</span>'}
                </td>

                <!-- Col 8: Video Mới Nhất -->
                <td><span style="font-size:12px; color:#cbd5e1;">${lastUploadText}</span></td>

                <!-- Col 9: Tần Suất Đăng -->
                <td><span class="badge badge-purple">${cadenceDesc}</span></td>

                <!-- Col 10: Video (Tải / Render) -->
                <td>
                    <div style="display:flex; gap:4px; flex-wrap:wrap;">
                        <span class="badge badge-blue" title="Video đã tải"><i class="fa-solid fa-download"></i> ${dlCount}</span>
                        <span class="badge badge-gold" title="Video đã render AI"><i class="fa-solid fa-wand-magic-sparkles"></i> ${rdCount}</span>
                    </div>
                </td>

                <!-- Col 11: Trạng Thái Toggle -->
                <td>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <label class="switch has-tooltip tooltip-top" data-tooltip="${isActive ? 'Bấm để Tạm ngưng (Dừng tải và render)' : 'Bấm để Bật Hoạt động (Tự động tải và render)'}">
                            <input type="checkbox" ${isActive ? 'checked' : ''} onchange="toggleChannelStatusInline('${escapeHtml(cid)}', this)">
                            <span class="slider round"></span>
                        </label>
                        ${statusBadge}
                    </div>
                </td>

                <!-- Col 12: Thao Tác -->
                <td style="text-align: center;">
                    <div class="action-dropdown-wrap">
                        <button type="button" class="btn-more-actions" id="btn-more-saved-${escapeHtml(cid)}" 
                            onclick="toggleActionMenu(event, 'saved-${escapeHtml(cid)}')" 
                            title="Tùy chọn thao tác">
                            <i class="fa-solid fa-ellipsis"></i>
                        </button>
                        <div class="action-dropdown-menu" id="action-menu-saved-${escapeHtml(cid)}">
                            <button type="button" class="action-dropdown-item" onclick="openChannelDetailModal('${escapeHtml(cid)}')">
                                <i class="fa-solid fa-circle-info" style="color:var(--accent-cyan);"></i> Xem chi tiết
                            </button>
                            <button type="button" class="action-dropdown-item" onclick="openChannelVideosModal('${escapeHtml(cid)}', '${escapeHtml(displayTitle || c.title || '')}')">
                                <i class="fa-solid fa-film" style="color:#00f2fe;"></i> Chi Tiết Video
                            </button>
                            <button type="button" class="action-dropdown-item" onclick="scanSingleChannel('${escapeHtml(cid)}', this)">
                                <i class="fa-solid fa-bolt" style="color:#fe2c55;"></i> Quét video mới ngay
                            </button>
                            <button type="button" class="action-dropdown-item" onclick="openChannelSettingsModal('${escapeHtml(cid)}')">
                                <i class="fa-solid fa-gear" style="color:#a855f7;"></i> Cài đặt kênh
                            </button>
                            <div class="dropdown-divider"></div>
                            <a href="${escapeHtml(chUrl)}" target="_blank" rel="noopener" class="action-dropdown-item" onclick="closeAllActionMenus()">
                                <i class="fa-brands fa-youtube" style="color:#ef4444;"></i> Mở YouTube
                            </a>
                            <button type="button" class="action-dropdown-item" onclick="copyChannelUrl('${escapeHtml(chUrl)}')">
                                <i class="fa-solid fa-link" style="color:#38bdf8;"></i> Sao chép URL
                            </button>
                            <button type="button" class="action-dropdown-item" onclick="copyTextToClipboard('${escapeHtml(cid)}', 'Đã sao chép Channel ID!')">
                                <i class="fa-solid fa-copy" style="color:#94a3b8;"></i> Sao chép ID
                            </button>
                            <div class="dropdown-divider"></div>
                            <button type="button" class="action-dropdown-item" onclick="clearChannelVideoHistory('${escapeHtml(cid)}', 'downloaded')">
                                <i class="fa-solid fa-file-arrow-down" style="color:#38bdf8;"></i> Xóa lịch sử video đã tải
                            </button>
                            <button type="button" class="action-dropdown-item" onclick="clearChannelVideoHistory('${escapeHtml(cid)}', 'rendered')">
                                <i class="fa-solid fa-film" style="color:#ec4899;"></i> Xóa lịch sử video đã render
                            </button>
                            <div class="dropdown-divider"></div>
                            <button type="button" class="action-dropdown-item text-danger" onclick="unsaveChannelFromList('${escapeHtml(cid)}', this)">
                                <i class="fa-solid fa-trash text-danger"></i> Bỏ lưu / Xóa kênh
                            </button>
                        </div>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

async function toggleChannelStatusInline(channelId, checkbox) {
    const newStatus = checkbox.checked ? 1 : 0;
    try {
        const res = await fetch('/api/youtube/channels/toggle-status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel_id: channelId, is_active: newStatus })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(data.state_label);
            const ch = cachedSavedChannels.find(c => c.channel_id === channelId);
            if (ch) {
                ch.is_active = data.is_active;
                ch.auto_download = data.is_active;
            }
            renderSavedChannelsTable();
            const activeCount = cachedSavedChannels.filter(c => c.is_active === 1).length;
            const elActive = document.getElementById('savedCountActive');
            if (elActive) elActive.textContent = activeCount;
        } else {
            checkbox.checked = !checkbox.checked;
            showToast('Lỗi: ' + (data.message || 'Không thể đổi trạng thái'), true);
        }
    } catch (err) {
        checkbox.checked = !checkbox.checked;
        showToast('Lỗi kết nối: ' + err.message, true);
    }
}

async function scanSingleChannel(channelId, btn) {
    closeAllActionMenus();
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    }
    showToast(`Đang quét RSS kênh ${channelId}...`);

    try {
        const res = await fetch('/api/youtube/channels/scan-now', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel_id: channelId })
        });
        const data = await res.json();
        if (data.status === 'success') {
            if (data.new_videos > 0) {
                showToast(`Đã tìm thấy & tải về ${data.new_videos} video mới từ kênh ${data.title}!`);
            } else {
                showToast(`Kênh ${data.title}: Chưa có video mới nào (đã kiểm tra ${data.total_rss || 0} mục RSS).`);
            }
            loadSavedChannels();
            loadVideos();
        } else {
            showToast('Lỗi: ' + (data.message || 'Không thể quét kênh'), true);
        }
    } catch (err) {
        showToast('Lỗi quét kênh: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

async function scanAllSavedChannels(btn) {
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang quét...';
    }
    showToast('Bắt đầu quét RSS toàn bộ kênh đang theo dõi...');

    const activeList = cachedSavedChannels.filter(c => c.is_active === 1);
    if (!activeList.length) {
        showToast('Không có kênh nào đang ở trạng thái Hoạt động!', true);
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
        return;
    }

    let totalNew = 0;
    for (const c of activeList) {
        try {
            const res = await fetch('/api/youtube/channels/scan-now', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel_id: c.channel_id })
            });
            const data = await res.json();
            if (data.status === 'success' && data.new_videos > 0) {
                totalNew += data.new_videos;
            }
        } catch (e) {
            console.warn('Lỗi quét kênh:', c.channel_id, e);
        }
    }

    showToast(`Quét hoàn tất: Phát hiện & tải về ${totalNew} video mới!`);
    loadSavedChannels();
    loadVideos();

    if (btn) {
        btn.disabled = false;
        btn.innerHTML = origHtml;
    }
}

async function unsaveChannelFromList(channelId, btn) {
    closeAllActionMenus();
    const ok = await showConfirmDialog({
        title: 'Bỏ Lưu Kênh YouTube',
        message: 'Bạn có chắc muốn BỎ LƯU và ngừng theo dõi kênh này?',
        details: 'Kênh sẽ không còn trong danh sách quét video tự động.',
        confirmText: 'Bỏ Theo Dõi',
        confirmClass: 'btn-danger'
    });
    if (!ok) return;

    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    }

    try {
        const res = await fetch('/api/youtube/unsave-channel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel_id: channelId })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Đã bỏ lưu kênh thành công!');
            loadSavedChannels();
            loadDashboardStats();
        } else {
            showToast('Lỗi khi bỏ lưu: ' + (data.message || 'Thất bại'), true);
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

function openChannelUrl(url) {
    closeAllActionMenus();
    if (url) window.open(url, '_blank');
}

function copyChannelUrl(url) {
    closeAllActionMenus();
    if (!url) return;
    navigator.clipboard.writeText(url).then(() => {
        showToast('Đã sao chép link kênh vào clipboard!');
    }).catch(err => {
        showToast('Không thể sao chép: ' + err.message, true);
    });
}

function openChannelSettingsModal(channelId) {
    closeAllActionMenus();
    const channel = cachedSavedChannels.find(c => c.channel_id === channelId);
    if (!channel) {
        showToast('Không tìm thấy thông tin kênh!', true);
        return;
    }
    activeModalChannel = channel;

    document.getElementById('settingChannelId').value = channel.channel_id;
    document.getElementById('modalChannelTitleHeader').textContent = channel.display_name || channel.title;
    document.getElementById('modalChannelIdSub').textContent = `ID: ${channel.channel_id} • URL: ${channel.url || 'N/A'}`;
    document.getElementById('settingDisplayName').value = channel.display_name || channel.title || '';
    document.getElementById('settingCustomProxy').value = channel.custom_proxy || '';
    document.getElementById('settingDownloadDir').value = channel.download_dir || '';
    document.getElementById('settingRenderDir').value = channel.render_dir || '';
    document.getElementById('settingIsActive').checked = channel.is_active === 1;
    document.getElementById('settingAutoDownload').checked = channel.auto_download === 1;
    document.getElementById('settingAutoRender').checked = channel.auto_render === 1;

    // Load và gán cài đặt BGM cho kênh
    populateChannelBgmSelect(channel.bgm_folder || '', channel.bgm_volume != null ? channel.bgm_volume : 0.15);

    document.getElementById('channelSettingsModal').classList.add('active');
}

function closeChannelSettingsModal() {
    document.getElementById('channelSettingsModal').classList.remove('active');
    activeModalChannel = null;
}

function openCurrentChannelYouTube() {
    if (activeModalChannel && activeModalChannel.url) {
        window.open(activeModalChannel.url, '_blank');
    } else if (activeModalChannel) {
        window.open('https://www.youtube.com/channel/' + activeModalChannel.channel_id, '_blank');
    }
}

function copyCurrentChannelUrl() {
    if (activeModalChannel) {
        const url = activeModalChannel.url || ('https://www.youtube.com/channel/' + activeModalChannel.channel_id);
        copyChannelUrl(url);
    }
}

function scanCurrentChannelNow(btn) {
    if (activeModalChannel) {
        scanSingleChannel(activeModalChannel.channel_id, btn);
    }
}

async function saveChannelSettings(btn) {
    const channelId = document.getElementById('settingChannelId')?.value;
    if (!channelId) return;

    const rawDisplayName = (document.getElementById('settingDisplayName')?.value || '').trim();
    const displayName = rawDisplayName || (activeModalChannel ? (activeModalChannel.title || '') : '').trim();
    const customProxy = (document.getElementById('settingCustomProxy')?.value || '').trim();
    const downloadDir = (document.getElementById('settingDownloadDir')?.value || '').trim();
    const renderDir = (document.getElementById('settingRenderDir')?.value || '').trim();
    const bgmVolumeInput = document.getElementById('settingBgmVolume');
    const rawBgmVolume = bgmVolumeInput ? bgmVolumeInput.value : '0.15';
    const bgmVolume = parseFloat(rawBgmVolume);
    if (customProxy && !isValidProxyFormat(customProxy)) {
        markInputError('settingCustomProxy', 'Định dạng Proxy không hợp lệ! Ví dụ: ip:port hoặc ip:port:user:pass');
        return;
    }
    if (isNaN(bgmVolume) || bgmVolume < 0 || bgmVolume > 1) {
        markInputError('settingBgmVolume', 'Âm lượng nhạc nền BGM phải từ 0.0 đến 1.0 (0% - 100%)!');
        return;
    }

    const payload = {
        channel_id: channelId,
        display_name: displayName,
        custom_proxy: customProxy,
        download_dir: downloadDir,
        render_dir: renderDir,
        is_active: document.getElementById('settingIsActive')?.checked ? 1 : 0,
        auto_download: document.getElementById('settingAutoDownload')?.checked ? 1 : 0,
        auto_render: document.getElementById('settingAutoRender')?.checked ? 1 : 0,
        bgm_folder: document.getElementById('settingBgmFolder')?.value || '',
        bgm_volume: bgmVolume
    };

    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang lưu...';
    }

    try {
        const res = await fetch('/api/youtube/channels/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast('✅ Đã lưu cấu hình kênh thành công!', 'success');
            closeChannelSettingsModal();
            loadSavedChannels();
        } else {
            showToast('Lỗi khi lưu: ' + (data.detail || data.message || 'Thất bại'), 'error');
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

async function clearChannelVideoHistory(channelId, target = 'downloaded') {
    closeAllActionMenus();
    const ch = (cachedSavedChannels || []).find(c => c.channel_id === channelId);
    const channelName = ch ? (ch.display_name || ch.title || channelId) : channelId;
    const isDownloaded = target === 'downloaded';
    const actionLabel = isDownloaded ? 'video đã tải' : 'video đã render';

    const ok = await showConfirmDialog({
        title: `Xóa Lịch Sử ${actionLabel.toUpperCase()}`,
        message: `Bạn có chắc muốn XÓA LỊCH SỬ ${actionLabel} của kênh "${channelName}"?`,
        details: 'Thao tác này cũng sẽ xóa các file trên máy tính để giải phóng dung lượng!',
        confirmText: 'Xác Nhận Xóa',
        confirmClass: 'btn-danger'
    });
    if (!ok) return;

    try {
        const res = await fetch('/api/youtube/channels/clear-history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel_id: channelId, delete_files: true, target: target })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(`Đã xóa ${data.deleted_videos} ${actionLabel} (${data.files_deleted} files) của kênh "${channelName}"!`);
            if (typeof loadSavedChannels === 'function') loadSavedChannels();
            if (typeof loadVideos === 'function') loadVideos();
            if (typeof loadPipelineStatus === 'function') loadPipelineStatus();
            if (typeof loadDashboardStats === 'function') loadDashboardStats();
        } else {
            showToast('Lỗi khi xóa lịch sử: ' + (data.message || 'Thất bại'), true);
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, true);
    }
}

async function clearChannelHistoryFromModal(btn) {
    if (!activeModalChannel) return;
    const cid = activeModalChannel.channel_id;
    const name = activeModalChannel.display_name || activeModalChannel.title;

    const ok = await showConfirmDialog({
        title: 'Xóa Toàn Bộ Lịch Sử & Tệp Tin',
        message: `Bạn có chắc muốn XÓA TOÀN BỘ lịch sử video đã tải và render của kênh "${name}"?`,
        details: 'Thao tác này cũng sẽ xóa các tệp tin trên đĩa!',
        confirmText: 'Xác Nhận Xóa',
        confirmClass: 'btn-danger'
    });
    if (!ok) return;

    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang xóa...';
    }

    try {
        const res = await fetch('/api/youtube/channels/clear-history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel_id: cid, delete_files: true })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(`Đã xóa ${data.deleted_videos} video (${data.files_deleted} files) của kênh này!`);
            loadSavedChannels();
            loadVideos();
            loadPipelineStatus();
        } else {
            showToast('Lỗi khi xóa lịch sử: ' + (data.message || 'Thất bại'), true);
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

async function deleteChannelFromModal(btn) {
    if (!activeModalChannel) return;
    const cid = activeModalChannel.channel_id;
    const name = activeModalChannel.display_name || activeModalChannel.title;

    const ok = await showConfirmDialog({
        title: 'Xóa Kênh Theo Dõi',
        message: `Xác nhận xóa hoàn toàn kênh "${name}" khỏi cơ sở dữ liệu theo dõi?`,
        details: 'Toàn bộ dữ liệu cấu hình theo dõi của kênh này sẽ bị loại bỏ.',
        confirmText: 'Xóa Kênh',
        confirmClass: 'btn-danger'
    });
    if (!ok) return;

    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    }

    try {
        const res = await fetch(`/api/youtube/channels/${cid}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(`Đã xóa kênh "${name}" thành công!`);
            closeChannelSettingsModal();
            loadSavedChannels();
            loadDashboardStats();
        } else {
            showToast('Lỗi khi xóa kênh: ' + (data.message || 'Thất bại'), true);
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// ==========================================
// 8. AUTOMATION PIPELINE, CAMPAIGNS & STUDIO
// ==========================================
function applyCachedSchedulerState() {
    try {
        const cached = localStorage.getItem('scheduler_running');
        if (cached === '0') {
            const masterLed = document.getElementById('masterSchedulerLed');
            const masterTitle = document.getElementById('masterSchedulerTitle');
            const masterBadge = document.getElementById('masterSchedulerBadge');
            const masterBtn = document.getElementById('btnToggleSchedulerMaster');
            const pipeScheduler = document.getElementById('pipelineSchedulerStatus');
            if (masterLed) masterLed.className = 'master-pulse-icon paused';
            if (masterTitle) masterTitle.textContent = 'HỆ THỐNG TỰ ĐỘNG: ĐÃ TẠM DỪNG';
            if (masterBadge) {
                masterBadge.className = 'badge badge-danger';
                masterBadge.textContent = 'Auto-Pilot Paused';
            }
            if (masterBtn) {
                masterBtn.className = 'btn btn-primary has-tooltip';
                masterBtn.innerHTML = '<i class="fa-solid fa-play"></i> <span>Bật Tự Động</span>';
                masterBtn.setAttribute('data-tooltip', 'Khởi động hệ thống tự động: Quét RSS, tải, render & đăng bài');
                masterBtn.removeAttribute('title');
            }
            if (pipeScheduler) {
                pipeScheduler.className = 'badge badge-secondary';
                pipeScheduler.innerHTML = '<i class="fa-solid fa-pause"></i> Scheduler: Tạm Dừng';
            }
        }
    } catch (e) {
        // Ignore localStorage error if disabled
    }
}

async function loadPipelineStatus() {
    try {
        const res = await fetch('/api/pipeline/status');
        const data = await res.json();

        if (data.scheduler_running !== undefined) {
            try {
                localStorage.setItem('scheduler_running', data.scheduler_running ? '1' : '0');
            } catch (e) { }
        }

        // 1. Top Badges
        const pipeActive = document.getElementById('pipeActiveChannels');
        if (pipeActive) pipeActive.textContent = `${data.active_channels || 0} Kênh Active`;

        const pipeDl = document.getElementById('pipeDownloadedCount');
        if (pipeDl) pipeDl.textContent = `${data.video_stats ? data.video_stats.downloaded : 0} Video Đã Tải`;

        const pipeRd = document.getElementById('pipeRenderedCount');
        if (pipeRd) pipeRd.textContent = `${data.video_stats ? data.video_stats.rendered : 0} Video Đã Render`;

        const pipeUp = document.getElementById('pipeUploadedCount');
        if (pipeUp) pipeUp.textContent = `${data.video_stats ? data.video_stats.uploaded : 0} Video Đã Đăng`;

        // 2. Master Banner Controls
        const masterLed = document.getElementById('masterSchedulerLed');
        const masterTitle = document.getElementById('masterSchedulerTitle');
        const masterBadge = document.getElementById('masterSchedulerBadge');
        const masterBtn = document.getElementById('btnToggleSchedulerMaster');
        const pipeScheduler = document.getElementById('pipelineSchedulerStatus');
        const interval = data.scheduler_interval_minutes || 15;

        const masterDesc = document.getElementById('masterSchedulerDesc');
        if (masterDesc) {
            masterDesc.innerHTML = `Chu kỳ quét RSS (${interval} phút) &rarr; Tự động tải MP4 &rarr; AI Render 9:16 Beta &rarr; Tự đăng lên TikTok GPM`;
        }
        const pipeRssMeta = document.getElementById('pipeRssIntervalMeta');
        if (pipeRssMeta) {
            pipeRssMeta.textContent = `Mỗi ${interval} phút qua XML YouTube`;
        }

        if (data.scheduler_running) {
            if (masterLed) masterLed.className = 'master-pulse-icon';
            if (masterTitle) masterTitle.textContent = 'HỆ THỐNG TỰ ĐỘNG: ĐANG HOẠT ĐỘNG';
            if (masterBadge) {
                masterBadge.className = 'badge badge-success';
                masterBadge.textContent = 'Auto-Pilot Active';
            }
            if (masterBtn) {
                masterBtn.className = 'btn btn-secondary has-tooltip';
                masterBtn.innerHTML = '<i class="fa-solid fa-pause"></i> <span>Tạm Dừng</span>';
                masterBtn.setAttribute('data-tooltip', `Tạm dừng toàn bộ quá trình tự động quét (${interval}p/lần) & đăng bài`);
                masterBtn.removeAttribute('title');
            }
            if (pipeScheduler) {
                pipeScheduler.className = 'badge badge-success';
                pipeScheduler.innerHTML = `<i class="fa-solid fa-circle-dot"></i> Scheduler: Đang Chạy (${interval}p/lần)`;
            }
        } else {
            if (masterLed) masterLed.className = 'master-pulse-icon paused';
            if (masterTitle) masterTitle.textContent = 'HỆ THỐNG TỰ ĐỘNG: ĐÃ TẠM DỪNG';
            if (masterBadge) {
                masterBadge.className = 'badge badge-danger';
                masterBadge.textContent = 'Auto-Pilot Paused';
            }
            if (masterBtn) {
                masterBtn.className = 'btn btn-primary has-tooltip';
                masterBtn.innerHTML = '<i class="fa-solid fa-play"></i> <span>Bật Tự Động</span>';
                masterBtn.setAttribute('data-tooltip', `Khởi động hệ thống tự động: Quét RSS ${interval}p/lần, tải, render 9:16 & đăng bài`);
                masterBtn.removeAttribute('title');
            }
            if (pipeScheduler) {
                pipeScheduler.className = 'badge badge-secondary';
                pipeScheduler.innerHTML = '<i class="fa-solid fa-pause"></i> Scheduler: Tạm Dừng';
            }
        }

        // 3. Raw Table
        const tbody = document.getElementById('pipelineTableBody');
        const recent = data.recent_pipeline || [];
        if (tbody) {
            if (!recent.length) {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-muted">Chưa có video nào trong luồng xử lý. Hãy quét và lưu kênh để bắt đầu tải tự động!</td></tr>`;
            } else {
                tbody.innerHTML = recent.map(v => {
                    const statusBadgeMap = {
                        'pending': '<span class="badge badge-info"><i class="fa-solid fa-clock"></i> Chờ tải</span>',
                        'downloaded': '<span class="badge badge-blue"><i class="fa-solid fa-cloud-arrow-down"></i> Đã tải gốc</span>',
                        'rendering': '<span class="badge badge-purple"><i class="fa-solid fa-spinner fa-spin"></i> Đang render AI</span>',
                        'rendered': '<span class="badge badge-gold"><i class="fa-solid fa-wand-magic-sparkles"></i> Đã render 9:16</span>',
                        'uploaded': '<span class="badge badge-success"><i class="fa-brands fa-tiktok"></i> Đã đăng TikTok</span>',
                        'error': '<span class="badge badge-danger"><i class="fa-solid fa-triangle-exclamation"></i> Lỗi</span>'
                    };
                    const statusHtml = statusBadgeMap[v.status] || `<span class="badge">${escapeHtml(v.status)}</span>`;

                    return `
                        <tr>
                            <td>#${v.id}</td>
                            <td>
                                <div class="table-text-truncate" style="max-width: 240px;" title="${escapeHtml(v.title || 'Video #' + v.id)}">
                                    <strong>${escapeHtml(v.title || 'Video #' + v.id)}</strong>
                                </div>
                            </td>
                            <td>
                                <span class="badge badge-cyan table-text-truncate" style="max-width: 140px; display:inline-block; vertical-align:middle;" title="${escapeHtml(v.channel_name || 'Kênh ngoài')}">${escapeHtml(v.channel_name || 'Kênh ngoài')}</span>
                            </td>
                            <td>${v.duration ? v.duration + 's' : 'N/A'}</td>
                            <td>${statusHtml}</td>
                            <td><span style="font-size:12px; color:var(--text-muted);">${escapeHtml(v.created_at || '')}</span></td>
                            <td>
                                <button class="btn btn-sm btn-secondary" onclick="switchTab('tab-video-studio'); selectStudioVideo('${v.yt_video_id || v.id}')" title="Mở Studio xem trước & chỉnh sửa">
                                    <i class="fa-solid fa-wand-magic-sparkles"></i>
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        }

        // 4. Kanban Columns
        renderKanbanPipeline(recent, data.recent_upload_tasks || []);
    } catch (err) {
        console.error('Lỗi khi tải trạng thái pipeline:', err);
    }
}

function renderKanbanPipeline(videos, uploadTasks) {
    const colDl = document.getElementById('kanbanColDownloaded');
    const colRd = document.getElementById('kanbanColRendered');
    const colSc = document.getElementById('kanbanColScheduled');
    const colUp = document.getElementById('kanbanColUploaded');

    const cntDl = document.getElementById('kanbanCountDownloaded');
    const cntRd = document.getElementById('kanbanCountRendered');
    const cntSc = document.getElementById('kanbanCountScheduled');
    const cntUp = document.getElementById('kanbanCountUploaded');

    const downloaded = videos.filter(v => v.status === 'downloaded');
    const rendered = videos.filter(v => v.status === 'rendered');
    const scheduled = uploadTasks.filter(t => t.status === 'queued' || t.status === 'processing' || t.status === 'failed');
    const uploaded = uploadTasks.filter(t => t.status === 'completed');

    if (cntDl) cntDl.textContent = downloaded.length;
    if (cntRd) cntRd.textContent = rendered.length;
    if (cntSc) cntSc.textContent = scheduled.length;
    if (cntUp) cntUp.textContent = uploaded.length;

    const renderCard = (v, actionType) => `
        <div class="kanban-task-card">
            <strong style="font-size:12px; color:#fff; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">${escapeHtml(v.title || 'Video #' + v.id)}</strong>
            <div style="display:flex; justify-content:space-between; align-items:center; font-size:11px; color:var(--text-muted);">
                <span><i class="fa-solid fa-clock"></i> ${v.duration || 65}s</span>
                <span class="badge badge-cyan" style="font-size:10px;">${escapeHtml(v.channel_name || 'Kênh')}</span>
            </div>
            <div style="display:flex; gap:6px; margin-top:4px;">
                ${actionType === 'render' ? `
                    <button class="btn btn-sm btn-primary" onclick="switchTab('tab-video-studio'); selectStudioVideo('${v.yt_video_id || v.id}')" style="width:100%; font-size:11px; padding:4px;">
                        <i class="fa-solid fa-wand-magic-sparkles"></i> Render 9:16
                    </button>
                ` : ''}
                ${actionType === 'upload' ? `
                    <button class="btn btn-sm btn-secondary" onclick="switchTab('tab-video-studio'); selectStudioVideo('${v.yt_video_id || v.id}')" style="flex:1; font-size:11px; padding:4px;">
                        <i class="fa-solid fa-eye"></i> Xem Thử
                    </button>
                    <button class="btn btn-sm btn-primary" onclick="openUploadModal('${v.id}')" style="flex:1; font-size:11px; padding:4px;">
                        <i class="fa-solid fa-cloud-arrow-up"></i> Đăng GPM
                    </button>
                ` : ''}
            </div>
        </div>
    `;

    if (colDl) {
        colDl.innerHTML = downloaded.length ? downloaded.map(v => renderCard(v, 'render')).join('') : '<div class="text-center py-4 text-muted" style="font-size:11px;">Không có video chờ render</div>';
    }
    if (colRd) {
        colRd.innerHTML = rendered.length ? rendered.map(v => renderCard(v, 'upload')).join('') : '<div class="text-center py-4 text-muted" style="font-size:11px;">Không có video sẵn sàng</div>';
    }
    if (colSc) {
        colSc.innerHTML = scheduled.length ? scheduled.map(t => {
            const nick = t.tiktok_username ? (t.tiktok_username.startsWith('@') ? t.tiktok_username : '@' + t.tiktok_username) : (t.gpm_profile_name || 'GPM Profile');
            const isFailed = t.status === 'failed';
            return `
            <div class="kanban-task-card" style="${isFailed ? 'border-color: rgba(239,68,68,0.4); background: rgba(239,68,68,0.05);' : ''}">
                <strong style="font-size:12px; color:#fff; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;" title="${escapeHtml(t.video_title || t.title || 'Task #' + t.id)}">
                    ${escapeHtml(t.video_title || t.title || 'Task #' + t.id)}
                </strong>
                <div style="font-size:11px; color:${isFailed ? '#ef4444' : 'var(--accent-gold)'}; display:flex; align-items:center; gap:5px; margin-top:2px;">
                    <i class="fa-brands fa-tiktok"></i>
                    <strong>${escapeHtml(nick)}</strong>
                    ${isFailed ? '<span class="badge badge-danger" style="font-size:9px; padding:1px 4px;">Lỗi Đăng</span>' : ''}
                </div>
                ${isFailed ? `
                    <div style="font-size:10px; color:#f87171; margin-top:3px; display:flex; justify-content:space-between; align-items:center; gap:4px;">
                        <span title="${escapeHtml(t.error_message || 'Lỗi khi upload')}" style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:140px;">
                            <i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(t.error_message || 'Thất bại')}
                        </span>
                        <button class="btn btn-sm btn-warning" onclick="retryUploadTask(${t.id})" style="font-size:10px; padding:2px 7px; white-space:nowrap;">
                            <i class="fa-solid fa-rotate-right"></i> Thử Lại
                        </button>
                    </div>
                ` : `
                    <div style="font-size:10.5px; color:var(--text-muted); display:flex; align-items:center; gap:4px;">
                        <i class="fa-regular fa-clock"></i> Hẹn: ${escapeHtml(t.scheduled_time || 'Đang chờ')}
                    </div>
                `}
            </div>
            `;
        }).join('') : '<div class="text-center py-4 text-muted" style="font-size:11px;">Không có video lên lịch</div>';
    }
    if (colUp) {
        colUp.innerHTML = uploaded.length ? uploaded.map(t => {
            const nick = t.tiktok_username ? (t.tiktok_username.startsWith('@') ? t.tiktok_username : '@' + t.tiktok_username) : (t.gpm_profile_name || 'GPM');
            return `
            <div class="kanban-task-card">
                <strong style="font-size:12px; color:#fff; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;" title="${escapeHtml(t.video_title || t.title || 'Task #' + t.id)}">
                    ${escapeHtml(t.video_title || t.title || 'Task #' + t.id)}
                </strong>
                <div style="font-size:11px; color:var(--accent-green); display:flex; align-items:center; gap:5px; margin-top:2px;">
                    <i class="fa-solid fa-circle-check"></i>
                    <strong>${escapeHtml(nick)}</strong>
                </div>
                <div style="font-size:10.5px; color:var(--text-muted);">${escapeHtml(t.uploaded_at ? t.uploaded_at.substring(0, 16) : 'Đã hoàn tất')}</div>
            </div>
            `;
        }).join('') : '<div class="text-center py-4 text-muted" style="font-size:11px;">Chưa có bài đăng</div>';
    }
}

async function retryUploadTask(taskId) {
    try {
        const res = await fetch(`/api/pipeline/retry-upload/${taskId}`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message || 'Đã đưa tác vụ trở lại hàng đợi!', 'success');
            if (typeof loadPipelineStatus === 'function') loadPipelineStatus();
        } else {
            showToast(data.detail || 'Không thể thử lại tác vụ', 'error');
        }
    } catch (e) {
        showToast('Lỗi kết nối khi thử lại tác vụ: ' + e.message, 'error');
    }
}

async function triggerProcessUploads() {
    try {
        const res = await fetch('/api/pipeline/process-uploads', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            showToast('Đang quét và tiến hành đăng video đến giờ...', 'info');
            setTimeout(() => {
                if (typeof loadPipelineStatus === 'function') loadPipelineStatus();
            }, 3000);
        } else {
            showToast(data.detail || 'Không thể kích hoạt đăng bài', 'error');
        }
    } catch (e) {
        showToast('Lỗi khi kích hoạt đăng bài: ' + e.message, 'error');
    }
}

// Master Scheduler Toggle
async function toggleMasterScheduler(btn) {
    if (btn) btn.disabled = true;
    try {
        const res = await fetch('/api/pipeline/toggle-scheduler', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success' || data.scheduler_running !== undefined) {
            const isRun = data.running !== undefined ? data.running : data.scheduler_running;
            try {
                localStorage.setItem('scheduler_running', isRun ? '1' : '0');
            } catch (e) { }
            showToast(isRun ? 'Đã khởi động Scheduler tự động!' : 'Đã tạm dừng Scheduler tự động.');
            loadPipelineStatus();
        } else {
            showToast('Lỗi thay đổi trạng thái scheduler', true);
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

// Scan All Channels
async function scanAllChannelsPipeline(btn) {
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Quét...';
    }
    showToast('Đang quét RSS feed toàn bộ kênh đã lưu...');
    try {
        const res = await fetch('/api/pipeline/scan-all', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(`Quét hoàn tất: Tìm thấy và tải ${data.new_videos} video mới!`);
            loadPipelineStatus();
            loadVideos();
            loadDashboardStats();
        } else {
            showToast('Lỗi khi quét kênh: ' + (data.message || 'Thất bại'), true);
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// ==========================================
// 9. AUTO CAMPAIGNS HUB (CHIẾN DỊCH TỰ ĐỘNG)
// ==========================================
async function loadCampaigns() {
    const grid = document.getElementById('campaignsFlowGrid');
    if (!grid) return;
    try {
        const res = await fetch('/api/campaigns');
        const campaigns = await res.json();
        cachedCampaigns = campaigns;

        const stepperCamp = document.getElementById('stepperCampaignStats');
        if (stepperCamp) {
            const activeCount = campaigns.filter(c => c.is_active === 1).length;
            stepperCamp.textContent = `${activeCount} chiến dịch đang chạy`;
        }

        if (!campaigns.length) {
            grid.innerHTML = `
                <div class="card-empty-state">
                    <i class="fa-solid fa-robot"></i>
                    <h4>Chưa có chiến dịch tự động nào</h4>
                    <p>Hãy tạo chiến dịch đầu tiên để kết nối Kênh YouTube nguồn với công thức Edit và Nick TikTok nhận video.</p>
                    <button class="btn btn-primary mt-3" onclick="openNewCampaignModal()">
                        <i class="fa-solid fa-plus"></i> Tạo Chiến Dịch Tự Động Đầu Tiên
                    </button>
                </div>
            `;
            return;
        }

        grid.innerHTML = campaigns.map(c => {
            const chCount = c.channel_count || (c.channel_ids_list ? c.channel_ids_list.length : 1);
            const gpmCount = c.gpm_count || (c.gpm_profile_ids_list ? c.gpm_profile_ids_list.length : 1);
            const chTitle = chCount > 1 ? `${chCount} Kênh YouTube Nguồn` : (c.channel_name || 'Kênh nguồn');
            const gpmTitle = gpmCount > 1 ? `${gpmCount} Dàn Nick TikTok` : (c.gpm_profile_name ? '@' + (c.tiktok_username || c.gpm_profile_name) : 'Nick GPM');

            const distBadge = c.distribution_mode === 'round_robin'
                ? '<span class="badge badge-cyan" title="Chống trùng: chia vòng tròn clip"><i class="fa-solid fa-arrows-spin"></i> Round-Robin (Không trùng)</span>'
                : (c.distribution_mode === 'equal_random'
                    ? '<span class="badge badge-purple"><i class="fa-solid fa-shuffle"></i> Ngẫu Nhiên</span>'
                    : '<span class="badge badge-gold"><i class="fa-solid fa-bullhorn"></i> Đăng Toàn Bộ</span>');

            let freqBadge = '';
            let freqText = 'Mỗi ngày';
            if (c.post_frequency === 'every_2_days') {
                freqBadge = '<span class="badge badge-purple" title="Đăng cách 2 ngày 1 lần"><i class="fa-solid fa-calendar-days"></i> Cách 2 ngày</span>';
                freqText = 'Cách 2 ngày/lần';
            } else if (c.post_frequency === 'every_3_days') {
                freqBadge = '<span class="badge badge-purple" title="Đăng cách 3 ngày 1 lần"><i class="fa-solid fa-calendar-days"></i> Cách 3 ngày</span>';
                freqText = 'Cách 3 ngày/lần';
            } else if (c.post_frequency === 'specific_days') {
                const daysMap = { 'mon': 'T2', 'tue': 'T3', 'wed': 'T4', 'thu': 'T5', 'fri': 'T6', 'sat': 'T7', 'sun': 'CN' };
                const daysStr = (c.post_days_of_week || '').split(',').map(d => daysMap[d.trim()] || d).join(', ');
                freqBadge = `<span class="badge badge-cyan" title="Các ngày: ${daysStr}"><i class="fa-solid fa-calendar-check"></i> ${daysStr}</span>`;
                freqText = daysStr;
            } else if (c.post_frequency === 'custom_interval') {
                freqBadge = `<span class="badge badge-purple" title="Khoảng cách: ${c.post_interval_days} ngày"><i class="fa-solid fa-hourglass-half"></i> Cách ${c.post_interval_days} ngày</span>`;
                freqText = `Cách ${c.post_interval_days} ngày`;
            } else {
                freqBadge = '<span class="badge badge-blue"><i class="fa-solid fa-calendar-days"></i> Mỗi ngày</span>';
            }

            const warmupBadge = c.warmup_mode ? '<span class="badge badge-gold" title="Chế độ warm-up nuôi nick mới"><i class="fa-solid fa-fire"></i> Warm-up</span>' : '';

            const bgmBadge = c.bgm_folder
                ? `<span class="badge badge-info" title="BGM: ${escapeHtml(c.bgm_folder)} (${Math.round((c.bgm_volume || 0.15) * 100)}%)"><i class="fa-solid fa-music"></i> Nhạc: ${escapeHtml(c.bgm_folder)}</span>`
                : '';

            const subBadge = c.subtitle_enabled
                ? `<span class="badge badge-gold" title="Phong cách: ${escapeHtml(c.subtitle_style || '')}"><i class="fa-solid fa-closed-captioning"></i> Phụ Đề AI Karaoke</span>`
                : '<span class="badge badge-secondary">Không phụ đề</span>';

            const dlDir = c.download_dir || 'data/downloads';
            const rdDir = c.render_dir || 'data/rendered';

            return `
            <div class="campaign-card ${c.is_active ? '' : 'campaign-paused'}">
                <div class="campaign-header-row">
                    <div class="campaign-header-left">
                        <span class="badge ${c.is_active ? 'badge-success' : 'badge-secondary'}">
                            <i class="fa-solid fa-circle-dot"></i> ${c.is_active ? 'Đang Chạy Auto' : 'Tạm Dừng'}
                        </span>
                        <h4 class="campaign-card-title has-tooltip" title="${escapeHtml(c.name)}" data-tooltip="${escapeHtml(c.name)}">${escapeHtml(c.name)}</h4>
                        ${distBadge}
                        ${freqBadge}
                        ${warmupBadge}
                    </div>
                    <div style="display:flex; gap:8px; align-items:center;">
                        <button class="btn btn-sm btn-secondary has-tooltip" onclick="triggerDirectCampaignRun(${c.id}, '${escapeHtml(c.name).replace(/'/g, "\\'")}')" data-tooltip="Quét RSS & chạy thử biên tập AI cho chiến dịch này ngay">
                            <i class="fa-solid fa-bolt text-gold"></i> Chạy Thử
                        </button>
                        <button class="btn btn-sm btn-secondary has-tooltip" onclick="openCampaignLogs(${c.id}, '${escapeHtml(c.name).replace(/'/g, "\\'")}')" data-tooltip="Xem dữ liệu & nhật ký hoạt động chiến dịch này">
                            <i class="fa-solid fa-list-check text-cyan"></i> Nhật Ký
                        </button>
                        <button class="btn btn-sm btn-secondary has-tooltip" onclick="openEditCampaignModal(${c.id})" data-tooltip="Chỉnh sửa cấu hình chiến dịch này">
                            <i class="fa-solid fa-pen-to-square text-cyan"></i> Sửa
                        </button>
                        <button class="btn btn-sm ${c.is_active ? 'btn-secondary' : 'btn-success'} has-tooltip" onclick="toggleCampaign(${c.id})" data-tooltip="${c.is_active ? 'Tạm dừng quy trình tự động của chiến dịch này' : 'Bật chạy lại chiến dịch này'}">
                            <i class="fa-solid ${c.is_active ? 'fa-pause' : 'fa-play'}"></i> ${c.is_active ? 'Tạm Dừng' : 'Kích Hoạt'}
                        </button>
                        <button class="btn btn-sm btn-danger has-tooltip tooltip-left" onclick="deleteCampaign(${c.id})" data-tooltip="Xóa vĩnh viễn chiến dịch này">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    </div>
                </div>

                <div class="campaign-pipeline-flow">
                    <!-- Node 1: Multi-Channels Source -->
                    <div class="pipeline-node">
                        <div class="node-icon bg-blue"><i class="fa-brands fa-youtube" style="color:#ff0000;"></i></div>
                        <div class="node-text">
                            <h5>${escapeHtml(chTitle)}</h5>
                            <p>${chCount > 1 ? `Nhóm ${chCount} kênh lấy video tự động` : 'Quét RSS mỗi 15 phút'}</p>
                            <span class="pipeline-dir-tag" title="Thư mục tải MP4 gốc"><i class="fa-regular fa-folder"></i> ${escapeHtml(dlDir)}</span>
                        </div>
                    </div>

                    <div class="flow-step-arrow"><i class="fa-solid fa-arrow-right"></i></div>

                    <!-- Node 2: Edit Recipe, Folders & Subtitles -->
                    <div class="pipeline-node">
                        <div class="node-icon bg-purple"><i class="fa-solid fa-wand-magic-sparkles"></i></div>
                        <div class="node-text">
                            <h5>${escapeHtml(c.aspect_ratio === '9:16_blur' ? '9:16 Nền Mờ' : (c.preset_name || 'Chuẩn Beta 9:16'))}</h5>
                            <p>${c.video_duration || 65}s Beta • Speed x${c.speed_factor} • ${c.flip_horizontal ? 'Lật hình' : 'Gốc'} • <strong>${c.clips_per_video || 3} clips/video</strong> • <span style="color:${c.add_part_label !== 0 ? 'var(--accent-cyan)' : 'var(--text-muted)'}; font-weight:600;">${c.add_part_label !== 0 ? 'Hiện Part' : 'Ẩn Part'}</span></p>
                            <div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:3px;">${subBadge}${bgmBadge}</div>
                            <span class="pipeline-dir-tag" title="Thư mục lưu video 9:16"><i class="fa-solid fa-folder-open"></i> ${escapeHtml(rdDir)}</span>
                        </div>
                    </div>

                    <div class="flow-step-arrow"><i class="fa-solid fa-arrow-right"></i></div>

                    <!-- Node 3: Target Multi-Profiles & Schedule -->
                    <div class="pipeline-node">
                        <div class="node-icon bg-gold"><i class="fa-brands fa-tiktok"></i></div>
                        <div class="node-text">
                            <h5>${escapeHtml(gpmTitle)}</h5>
                            <p>${freqText} • ${c.daily_limit} video/ngày</p>
                            <span class="pipeline-dir-tag" style="color:var(--accent-gold);"><i class="fa-regular fa-clock"></i> Khung: ${escapeHtml(c.post_schedule || '11:30, 18:00, 20:30')}${c.random_delay_minutes ? ' (&plusmn;' + c.random_delay_minutes + 'p)' : ''}</span>
                            <span class="pipeline-dir-tag" style="color:#10b981; margin-top:2px;" title="Giãn cách an toàn tối thiểu giữa các lần đăng trên cùng 1 nick"><i class="fa-solid fa-hourglass-half"></i> Giãn cách: ${c.min_post_interval_minutes ? c.min_post_interval_minutes + 'p' : 'Toàn cục'}</span>
                        </div>
                    </div>
                </div>

                <div class="campaign-footer-row">
                    <div class="campaign-footer-meta">
                        <span class="campaign-footer-meta-item">
                            <i class="fa-regular fa-calendar" style="color:var(--text-muted);"></i> Tạo lúc: ${escapeHtml(c.created_at || '')}
                        </span>
                        <span class="campaign-footer-meta-item" style="color:var(--accent-cyan);">
                            <i class="fa-solid fa-bolt"></i> Phân phối: ${chCount} kênh &rarr; ${gpmCount} nick GPM (${c.distribution_mode === 'round_robin' ? 'Xoay vòng không trùng clip' : 'Chia đều'})
                        </span>
                    </div>
                    <a href="javascript:void(0)" onclick="openCampaignLogs(${c.id}, '${escapeHtml(c.name)}')" class="campaign-history-link has-tooltip" data-tooltip="Xem nhật ký & tỷ lệ thành công">
                        <i class="fa-solid fa-chart-line"></i> Xem Lịch Sử Hoạt Động &rarr;
                    </a>
                </div>
            </div>
            `;
        }).join('');
    } catch (err) {
        console.error('Lỗi nạp chiến dịch:', err);
    }
}

// Global cached lists for modal
let modalAllSavedChannels = [];
let modalAllGpmProfiles = [];

async function openNewCampaignModal() {
    const modal = document.getElementById('newCampaignModal');
    if (!modal) return;

    // Reset inputs
    const nameInput = document.getElementById('campaignNameInput');
    if (nameInput) nameInput.value = '';
    const minDurInput = document.getElementById('campaignMinDurationInput');
    if (minDurInput) minDurInput.value = '';
    const maxDurInput = document.getElementById('campaignMaxDurationInput');
    if (maxDurInput) maxDurInput.value = '';

    const clipsInput = document.getElementById('campaignClipsPerVideoInput');
    if (clipsInput) clipsInput.value = '3';
    handleCampaignClipsInputChange('new', 3);

    const chListEl = document.getElementById('campaignChannelsList');
    const gpmListEl = document.getElementById('campaignGpmList');

    if (chListEl) chListEl.innerHTML = '<div class="text-muted text-center py-2"><i class="fa-solid fa-spinner fa-spin"></i> Đang nạp danh sách kênh...</div>';
    if (gpmListEl) gpmListEl.innerHTML = '<div class="text-muted text-center py-2"><i class="fa-solid fa-spinner fa-spin"></i> Đang nạp profile GPMLogin...</div>';

    modal.classList.add('show');

    // 1. Fetch Saved Channels
    try {
        const res = await fetch('/api/youtube/channels');
        modalAllSavedChannels = await res.json();
        renderCampaignChannelsCheckboxes(modalAllSavedChannels);
    } catch (e) {
        if (chListEl) chListEl.innerHTML = '<div class="text-danger text-center py-2">Lỗi nạp danh sách kênh YouTube</div>';
    }

    // 2. Fetch GPM Profiles
    try {
        const res = await fetch('/api/gpm/profiles');
        modalAllGpmProfiles = await res.json();
        renderCampaignGpmCheckboxes(modalAllGpmProfiles);
    } catch (e) {
        if (gpmListEl) gpmListEl.innerHTML = '<div class="text-danger text-center py-2">Lỗi nạp danh sách profile GPMLogin</div>';
    }

    // 3. Restore persisted folder defaults from SQLite settings
    try {
        const defRes = await fetch('/api/settings/defaults');
        const defData = await defRes.json();
        const dlInput = document.getElementById('campaignDownloadDir');
        const rdInput = document.getElementById('campaignRenderDir');
        if (dlInput && defData.download_dir) dlInput.value = defData.download_dir;
        if (rdInput && defData.render_dir) rdInput.value = defData.render_dir;
    } catch (_) { }
}

function renderCampaignChannelsCheckboxes(channels) {
    const chListEl = document.getElementById('campaignChannelsList');
    if (!chListEl) return;

    if (!channels.length) {
        chListEl.innerHTML = `
            <div class="text-muted text-center py-3" style="font-size:12px;">
                Chưa có kênh nào được lưu. Hãy qua tab <strong>"1. Nguồn YouTube"</strong> để quét và lưu kênh trước!
            </div>
        `;
        updateSelectedChannelsCount();
        return;
    }

    chListEl.innerHTML = channels.map((ch, idx) => `
        <label class="multi-select-item" style="display:flex; align-items:center; gap:10px; padding:6px 8px; border-radius:4px; cursor:pointer; font-size:12.5px; border-bottom:1px solid rgba(255,255,255,0.03);">
            <input type="checkbox" class="campaign-ch-check" value="${escapeHtml(ch.channel_id)}" ${idx < 3 ? 'checked' : ''} onchange="updateSelectedChannelsCount()">
            <i class="fa-brands fa-youtube" style="color:#ff0000; font-size:14px;"></i>
            <span style="font-weight:600; color:#fff; flex:1;">${escapeHtml(ch.display_name || ch.title)}</span>
            <span style="font-size:11px; color:var(--accent-cyan);">${formatNumber(ch.subscriber_count || 0)} subs</span>
            <span class="badge badge-secondary" style="font-size:10px;">${escapeHtml(ch.country || 'US')}</span>
        </label>
    `).join('');

    updateSelectedChannelsCount();
}

function renderCampaignGpmCheckboxes(profiles) {
    const gpmListEl = document.getElementById('campaignGpmList');
    if (!gpmListEl) return;

    if (!profiles.length) {
        gpmListEl.innerHTML = `
            <div class="text-muted text-center py-3" style="font-size:12px;">
                Chưa có profile GPMLogin nào. Hãy bấm <strong>"Đồng Bộ GPM"</strong> ở tab "Dàn Nick TikTok"!
            </div>
        `;
        updateSelectedGpmCount();
        return;
    }

    gpmListEl.innerHTML = profiles.map((p, idx) => `
        <label class="multi-select-item" style="display:flex; align-items:center; gap:10px; padding:6px 8px; border-radius:4px; cursor:pointer; font-size:12.5px; border-bottom:1px solid rgba(255,255,255,0.03);">
            <input type="checkbox" class="campaign-gpm-check" value="${p.id}" ${idx < 3 ? 'checked' : ''} onchange="updateSelectedGpmCount()">
            <i class="fa-solid fa-robot" style="color:var(--accent-gold); font-size:14px;"></i>
            <span style="font-weight:600; color:#fff; flex:1;">${escapeHtml(p.name)}</span>
            <span style="font-size:11px; color:var(--accent-gold);">@${escapeHtml(p.tiktok_username || 'Chưa gắn')}</span>
            <span class="badge ${p.eligible_10k ? 'badge-success' : 'badge-secondary'}" style="font-size:10px;">${(p.followers_count || 0).toLocaleString()} flw</span>
        </label>
    `).join('');

    updateSelectedGpmCount();
}

function updateSelectedChannelsCount() {
    const checked = document.querySelectorAll('.campaign-ch-check:checked');
    const badge = document.getElementById('campaignSelectedChannelsCount');
    if (badge) badge.textContent = `Đã chọn: ${checked.length} kênh`;
}

function updateSelectedGpmCount() {
    const checked = document.querySelectorAll('.campaign-gpm-check:checked');
    const badge = document.getElementById('campaignSelectedGpmCount');
    if (badge) badge.textContent = `Đã chọn: ${checked.length} nick`;
}

function selectAllCampaignChannels(select) {
    const boxes = document.querySelectorAll('.campaign-ch-check');
    boxes.forEach(b => {
        if (b.closest('label').style.display !== 'none') {
            b.checked = select;
        }
    });
    updateSelectedChannelsCount();
}

function selectAllCampaignGpm(select) {
    const boxes = document.querySelectorAll('.campaign-gpm-check');
    boxes.forEach(b => {
        if (b.closest('label').style.display !== 'none') {
            b.checked = select;
        }
    });
    updateSelectedGpmCount();
}

function filterCampaignChannelList(query) {
    const q = (query || '').toLowerCase().trim();
    const items = document.querySelectorAll('#campaignChannelsList .multi-select-item');
    items.forEach(item => {
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(q) ? 'flex' : 'none';
    });
}

function filterCampaignGpmList(query) {
    const q = (query || '').toLowerCase().trim();
    const items = document.querySelectorAll('#campaignGpmList .multi-select-item');
    items.forEach(item => {
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(q) ? 'flex' : 'none';
    });
}

function onCampaignFrequencyChange(val) {
    const customWrap = document.getElementById('campaignCustomIntervalWrap');
    const daysWrap = document.getElementById('campaignDaysOfWeekWrap');
    if (customWrap) customWrap.style.display = val === 'custom_interval' ? 'block' : 'none';
    if (daysWrap) daysWrap.style.display = val === 'specific_days' ? 'block' : 'none';
}

function setCampaignSchedulePreset(val) {
    const inp = document.getElementById('campaignScheduleInput');
    if (inp) inp.value = val;
}

async function browseFolderForInput(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    showToast('Đang mở hộp thoại chọn thư mục Windows...');
    try {
        const res = await fetch('/api/utils/browse-folder', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success' && data.path) {
            input.value = data.path;
            showToast(`Đã chọn: ${data.path}`);
        } else if (data.status === 'cancelled') {
            // User cancelled folder picker
        } else if (data.status === 'error') {
            showToast('Lỗi mở hộp thoại chọn thư mục: ' + (data.message || 'Không rõ'), true);
        }
    } catch (err) {
        showToast('Lỗi kết nối máy chủ: ' + err.message, true);
    }
}

function closeNewCampaignModal() {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
        document.activeElement.blur();
    }
    const modal = document.getElementById('newCampaignModal');
    if (modal) {
        modal.classList.remove('show');
        modal.classList.remove('active');
    }
}

async function handleCreateCampaignSubmit(e) {
    e.preventDefault();
    const btn = document.getElementById('btnSubmitCampaign');

    // Validate Campaign Name
    const campNameInput = document.getElementById('campaignNameInput');
    const campName = campNameInput ? campNameInput.value.trim() : '';

    // 1. Gather Selected Channels
    const chBoxes = document.querySelectorAll('.campaign-ch-check:checked');
    const selectedChannelIds = Array.from(chBoxes).map(b => b.value);
    if (selectedChannelIds.length === 0) {
        showToast('⚠️ Vui lòng chọn ít nhất 1 kênh YouTube nguồn (hoặc chọn nhiều kênh 1, 2, 3...)!', 'warning');
        return;
    }

    // 2. Gather Selected GPM Profiles
    const gpmBoxes = document.querySelectorAll('.campaign-gpm-check:checked');
    const selectedGpmIds = Array.from(gpmBoxes).map(b => parseInt(b.value, 10)).filter(id => !isNaN(id));
    if (selectedGpmIds.length === 0) {
        showToast('⚠️ Vui lòng chọn ít nhất 1 Profile GPMLogin nhận video (hoặc chọn nhóm nick a, b, c...)!', 'warning');
        return;
    }

    // 1. Validate daily_limit
    const dailyLimitInput = document.getElementById('campaignDailyLimitInput');
    const rawDailyLimit = parseInt(dailyLimitInput?.value, 10);
    if (isNaN(rawDailyLimit) || rawDailyLimit < 1) {
        markInputError('campaignDailyLimitInput', 'Giới hạn video/ngày trên mỗi nick phải là số nguyên >= 1!');
        return;
    }
    const safeDailyLimit = Math.max(1, rawDailyLimit);

    // 2. Validate post_schedule
    const scheduleInput = document.getElementById('campaignScheduleInput');
    const scheduleRaw = (scheduleInput?.value || '').trim();
    const rawSlots = scheduleRaw.split(',').map(s => s.trim()).filter(Boolean);
    const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
    const invalidSlot = rawSlots.find(s => !timeRegex.test(s));
    if (!rawSlots.length || invalidSlot) {
        markInputError('campaignScheduleInput', `Khung giờ đăng không hợp lệ: "${invalidSlot || 'trống'}". Định dạng chuẩn: HH:MM`);
        return;
    }
    const safeSlots = Array.from(new Set(rawSlots.map(s => {
        const [h, m] = s.split(':');
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    })));
    const cleanScheduleStr = safeSlots.join(', ');

    // Gather frequency & advanced options
    const freq = document.getElementById('campaignFrequencySelect')?.value || 'daily';
    let intervalDays = 1;
    if (freq === 'every_2_days') intervalDays = 2;
    else if (freq === 'every_3_days') intervalDays = 3;
    else if (freq === 'custom_interval') {
        const customIntVal = parseInt(document.getElementById('campaignCustomIntervalInput')?.value, 10);
        if (isNaN(customIntVal) || customIntVal < 1 || customIntVal > 365) {
            markInputError('campaignCustomIntervalInput', 'Chu kỳ lặp lại phải từ 1 đến 365 ngày!');
            return;
        }
        intervalDays = customIntVal;
    }

    const minDurVal = document.getElementById('campaignMinDurationInput')?.value.trim();
    const maxDurVal = document.getElementById('campaignMaxDurationInput')?.value.trim();
    if (minDurVal && maxDurVal) {
        const minD = parseInt(minDurVal, 10);
        const maxD = parseInt(maxDurVal, 10);
        if (minD >= maxD) {
            markInputError('campaignMinDurationInput', 'Thời lượng tối thiểu phải nhỏ hơn thời lượng tối đa!');
            return;
        }
    }

    const clipsPerVid = parseInt(document.getElementById('campaignClipsPerVideoInput')?.value, 10) || 3;
    if (clipsPerVid < 1 || clipsPerVid > 20) {
        markInputError('campaignClipsPerVideoInput', 'Số phần cắt mỗi video phải từ 1 đến 20!');
        return;
    }

    const bgmVol = parseFloat(document.getElementById('campaignBgmVolume')?.value || 0.15);
    if (isNaN(bgmVol) || bgmVol < 0 || bgmVol > 1) {
        markInputError('campaignBgmVolume', 'Âm lượng nhạc nền BGM phải từ 0.0 đến 1.0 (0% - 100%)!');
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Kích Hoạt...';
    }

    const dowBoxes = document.querySelectorAll('.campaign-dow-check:checked');
    const daysOfWeek = Array.from(dowBoxes).map(b => b.value).join(',');
    const randomDelay = parseInt(document.getElementById('campaignRandomDelaySelect')?.value, 10) || 10;
    const warmup = document.getElementById('campaignWarmupSwitch')?.checked ? 1 : 0;

    const payload = {
        name: campName || `Chiến Dịch Auto ${selectedChannelIds.length} Kênh -> ${selectedGpmIds.length} Nick`,
        channel_id: selectedChannelIds[0],
        channel_ids: selectedChannelIds,
        gpm_profile_id: selectedGpmIds[0],
        gpm_profile_ids: selectedGpmIds,
        distribution_mode: document.getElementById('campaignDistributionMode')?.value || 'round_robin',
        download_dir: document.getElementById('campaignDownloadDir')?.value.trim() || 'data/downloads',
        render_dir: document.getElementById('campaignRenderDir')?.value.trim() || 'data/rendered',
        aspect_ratio: document.getElementById('campaignAspectRatio')?.value || '9:16_blur',
        preset_name: document.getElementById('campaignAspectRatio')?.value === '9:16_blur' ? 'TikTok Beta Chuẩn 9:16 (Nền Mờ)' : 'TikTok Chuẩn 9:16',
        video_duration: parseInt(document.getElementById('campaignVideoDuration')?.value, 10) || 65,
        min_video_duration: minDurVal ? parseInt(minDurVal, 10) : null,
        max_video_duration: maxDurVal ? parseInt(maxDurVal, 10) : null,
        ai_model: document.getElementById('campaignAiModel')?.value || 'default',
        ai_provider: (document.getElementById('campaignAiModel')?.value || '').startsWith('gemini') ? 'gemini' : ((document.getElementById('campaignAiModel')?.value || '').startsWith('gpt') ? 'openai' : 'deepseek'),
        subtitle_enabled: document.getElementById('campaignSubtitleSwitch')?.checked ? 1 : 0,
        subtitle_style: document.getElementById('campaignSubtitleStyle')?.value || 'karaoke_yellow',
        add_part_label: document.getElementById('campaignAddPartLabelSwitch')?.checked ? 1 : 0,
        clips_per_video: clipsPerVid,
        speed_factor: document.getElementById('campaignSpeedSwitch')?.checked ? 1.03 : 1.0,
        flip_horizontal: document.getElementById('campaignFlipSwitch')?.checked ? 1 : 0,
        daily_limit: safeDailyLimit,
        post_schedule: cleanScheduleStr,
        post_frequency: freq,
        post_interval_days: intervalDays,
        post_days_of_week: daysOfWeek || 'mon,tue,wed,thu,fri,sat,sun',
        random_delay_minutes: randomDelay,
        min_post_interval_minutes: document.getElementById('campaignMinPostIntervalSelect')?.value ? parseInt(document.getElementById('campaignMinPostIntervalSelect').value, 10) : null,
        warmup_mode: warmup,
        bgm_folder: document.getElementById('campaignBgmSwitch')?.checked ? (document.getElementById('campaignBgmFolder')?.value || '') : '',
        bgm_volume: bgmVol,
        is_active: 1
    };

    try {
        const res = await fetch('/api/campaigns', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`✅ Đã tạo chiến dịch tự động thành công! (${selectedChannelIds.length} kênh &rarr; ${selectedGpmIds.length} nick TikTok)`, 'success');
            closeNewCampaignModal();
            loadCampaigns();
            loadPipelineStatus();
        } else {
            showToast('Lỗi: ' + (data.detail || data.message || 'Không thể tạo chiến dịch'), 'error');
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-rocket"></i> Kích Hoạt Chiến Dịch Tự Động';
        }
    }
}

async function toggleCampaign(id) {
    try {
        const res = await fetch(`/api/campaigns/${id}/toggle`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(data.is_active ? '✅ Đã kích hoạt chiến dịch!' : '⏸️ Đã tạm dừng chiến dịch.');
            loadCampaigns();
        }
    } catch (err) {
        showToast('Lỗi: ' + err.message, true);
    }
}

async function deleteCampaign(id) {
    const camp = cachedCampaigns.find(c => c.id === id);
    const rawName = camp ? (camp.name || `Chiến dịch #${id}`) : `Chiến dịch #${id}`;
    const campName = rawName.length > 36 ? rawName.slice(0, 33) + '...' : rawName;
    const ok = await showConfirmDialog({
        title: 'Xóa Chiến Dịch Tự Động',
        message: `Bạn có chắc chắn muốn xóa chiến dịch "${campName}"?`,
        details: 'Các thiết lập tự động hóa, chu kỳ quét RSS và lịch đăng của chiến dịch này sẽ dừng ngay lập tức.',
        confirmText: 'Xóa Chiến Dịch',
        confirmClass: 'btn-danger'
    });
    if (!ok) return;

    try {
        const res = await fetch(`/api/campaigns/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Đã xóa chiến dịch thành công!');
            loadCampaigns();
        }
    } catch (err) {
        showToast('Lỗi: ' + err.message, true);
    }
}

// ==========================================
// 9.1 EDIT CAMPAIGN MODAL LOGIC
// ==========================================
let editCampaignOriginalData = null;

async function openEditCampaignModal(id) {
    const modal = document.getElementById('editCampaignModal');
    if (!modal) return;

    modal.classList.add('show');
    modal.classList.add('active');
    const chListEl = document.getElementById('editCampaignChannelsList');
    const gpmListEl = document.getElementById('editCampaignGpmList');
    if (chListEl) chListEl.innerHTML = '<div class="text-muted text-center py-2"><i class="fa-solid fa-spinner fa-spin"></i> Đang nạp danh sách kênh...</div>';
    if (gpmListEl) gpmListEl.innerHTML = '<div class="text-muted text-center py-2"><i class="fa-solid fa-spinner fa-spin"></i> Đang nạp profile GPMLogin...</div>';

    try {
        // Fetch campaign details
        const res = await fetch(`/api/campaigns/${id}`);
        const c = await res.json();
        editCampaignOriginalData = c;

        document.getElementById('editCampaignId').value = c.id;
        document.getElementById('editCampaignNameInput').value = c.name || '';

        // Channels & Profiles lists
        if (!modalAllSavedChannels || !modalAllSavedChannels.length) {
            try {
                const chRes = await fetch('/api/youtube/channels');
                modalAllSavedChannels = await chRes.json();
            } catch (_) { }
        }
        if (!modalAllGpmProfiles || !modalAllGpmProfiles.length) {
            try {
                const gpmRes = await fetch('/api/gpm/profiles');
                modalAllGpmProfiles = await gpmRes.json();
            } catch (_) { }
        }

        renderEditCampaignChannelsCheckboxes(modalAllSavedChannels, c.channel_ids_list || []);
        renderEditCampaignGpmCheckboxes(modalAllGpmProfiles, c.gpm_profile_ids_list || []);

        // Directories
        document.getElementById('editCampaignDownloadDir').value = c.download_dir || 'data/downloads';
        document.getElementById('editCampaignRenderDir').value = c.render_dir || 'data/rendered';

        // Edit Recipe
        const aspectSel = document.getElementById('editCampaignAspectRatio');
        if (aspectSel) aspectSel.value = c.aspect_ratio || '9:16_blur';

        const durSel = document.getElementById('editCampaignVideoDuration');
        if (durSel) durSel.value = String(c.video_duration || 65);

        const minDurInput = document.getElementById('editCampaignMinDurationInput');
        if (minDurInput) minDurInput.value = (c.min_video_duration != null) ? c.min_video_duration : '';

        const maxDurInput = document.getElementById('editCampaignMaxDurationInput');
        if (maxDurInput) maxDurInput.value = (c.max_video_duration != null) ? c.max_video_duration : '';

        const aiModelSel = document.getElementById('editCampaignAiModel');
        if (aiModelSel) aiModelSel.value = c.ai_model || 'default';

        const subSwitch = document.getElementById('editCampaignSubtitleSwitch');
        if (subSwitch) subSwitch.checked = c.subtitle_enabled === 1;

        const subStyle = document.getElementById('editCampaignSubtitleStyle');
        if (subStyle) subStyle.value = c.subtitle_style || 'karaoke_yellow';

        const flipSwitch = document.getElementById('editCampaignFlipSwitch');
        if (flipSwitch) flipSwitch.checked = c.flip_horizontal === 1;

        const clipsPerVidInput = document.getElementById('editCampaignClipsPerVideoInput');
        const clipsVal = c.clips_per_video || 3;
        if (clipsPerVidInput) clipsPerVidInput.value = clipsVal;
        handleCampaignClipsInputChange('edit', clipsVal);
        if (clipsVal > 1) {
            const partSwitch = document.getElementById('editCampaignAddPartLabelSwitch');
            if (partSwitch) partSwitch.checked = c.add_part_label !== 0;
        }

        const speedSwitch = document.getElementById('editCampaignSpeedSwitch');
        if (speedSwitch) speedSwitch.checked = (c.speed_factor && c.speed_factor > 1.0);

        // Multi-Account & Schedule
        const distMode = document.getElementById('editCampaignDistributionMode');
        if (distMode) distMode.value = c.distribution_mode || 'round_robin';

        const dailyLim = document.getElementById('editCampaignDailyLimitInput');
        if (dailyLim) dailyLim.value = c.daily_limit || 3;

        const freqSel = document.getElementById('editCampaignFrequencySelect');
        if (freqSel) freqSel.value = c.post_frequency || 'daily';
        onEditCampaignFrequencyChange(c.post_frequency || 'daily');

        const customInt = document.getElementById('editCampaignCustomIntervalInput');
        if (customInt) customInt.value = c.post_interval_days || 2;

        // Check days of week
        const dows = (c.post_days_of_week || 'mon,tue,wed,thu,fri,sat,sun').split(',').map(s => s.trim().toLowerCase());
        document.querySelectorAll('.edit-campaign-dow-check').forEach(chk => {
            chk.checked = dows.includes(chk.value.toLowerCase());
        });

        const schedInput = document.getElementById('editCampaignScheduleInput');
        if (schedInput) schedInput.value = c.post_schedule || '11:30, 18:00, 20:30';

        const randDelay = document.getElementById('editCampaignRandomDelaySelect');
        if (randDelay) randDelay.value = String(c.random_delay_minutes !== undefined ? c.random_delay_minutes : 10);

        const editMinInterval = document.getElementById('editCampaignMinPostIntervalSelect');
        if (editMinInterval) editMinInterval.value = c.min_post_interval_minutes ? String(c.min_post_interval_minutes) : '';

        const warmup = document.getElementById('editCampaignWarmupSwitch');
        if (warmup) warmup.checked = c.warmup_mode === 1;

        // BGM restore
        const hasBgm = Boolean(c.bgm_folder && c.bgm_folder.trim());
        const bgmSwitch = document.getElementById('editCampaignBgmSwitch');
        const bgmWrap = document.getElementById('editCampaignBgmSettingsWrap');
        if (bgmSwitch) bgmSwitch.checked = hasBgm;
        if (bgmWrap) bgmWrap.style.display = hasBgm ? 'grid' : 'none';

        const bgmFolderSel = document.getElementById('editCampaignBgmFolder');
        if (bgmFolderSel) bgmFolderSel.value = c.bgm_folder || '';
        const bgmVolInput = document.getElementById('editCampaignBgmVolume');
        const bgmVolVal = document.getElementById('editCampaignBgmVolumeVal');
        if (bgmVolInput) {
            bgmVolInput.value = c.bgm_volume != null ? c.bgm_volume : 0.15;
            if (bgmVolVal) bgmVolVal.textContent = Math.round(bgmVolInput.value * 100) + '%';
        }

    } catch (err) {
        showToast('Lỗi nạp thông tin chiến dịch: ' + err.message, true);
        closeEditCampaignModal();
    }
}

function closeEditCampaignModal() {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
        document.activeElement.blur();
    }
    const modal = document.getElementById('editCampaignModal');
    if (modal) {
        modal.classList.remove('show');
        modal.classList.remove('active');
    }
}

function renderEditCampaignChannelsCheckboxes(channels, selectedIds = []) {
    const chListEl = document.getElementById('editCampaignChannelsList');
    if (!chListEl) return;

    if (!channels || !channels.length) {
        chListEl.innerHTML = '<div class="text-muted text-center py-3" style="font-size:12px;">Chưa có kênh nào được lưu.</div>';
        updateEditSelectedChannelsCount();
        return;
    }

    const selSet = new Set((selectedIds || []).map(String));
    chListEl.innerHTML = channels.map(ch => {
        const isChecked = selSet.has(String(ch.channel_id));
        return `
            <label class="multi-select-item" style="display:flex; align-items:center; gap:10px; padding:6px 8px; border-radius:4px; cursor:pointer; font-size:12.5px; border-bottom:1px solid rgba(255,255,255,0.03);">
                <input type="checkbox" class="edit-campaign-ch-check" value="${escapeHtml(ch.channel_id)}" ${isChecked ? 'checked' : ''} onchange="updateEditSelectedChannelsCount()">
                <i class="fa-brands fa-youtube" style="color:#ff0000; font-size:14px;"></i>
                <span style="font-weight:600; color:#fff; flex:1;">${escapeHtml(ch.display_name || ch.title)}</span>
                <span style="font-size:11px; color:var(--accent-cyan);">${formatNumber(ch.subscriber_count || 0)} subs</span>
                <span class="badge badge-secondary" style="font-size:10px;">${escapeHtml(ch.country || 'US')}</span>
            </label>
        `;
    }).join('');

    updateEditSelectedChannelsCount();
}

function renderEditCampaignGpmCheckboxes(profiles, selectedIds = []) {
    const gpmListEl = document.getElementById('editCampaignGpmList');
    if (!gpmListEl) return;

    if (!profiles || !profiles.length) {
        gpmListEl.innerHTML = '<div class="text-muted text-center py-3" style="font-size:12px;">Chưa có profile GPMLogin nào.</div>';
        updateEditSelectedGpmCount();
        return;
    }

    const selSet = new Set((selectedIds || []).map(String));
    gpmListEl.innerHTML = profiles.map(p => {
        const isChecked = selSet.has(String(p.id));
        return `
            <label class="multi-select-item" style="display:flex; align-items:center; gap:10px; padding:6px 8px; border-radius:4px; cursor:pointer; font-size:12.5px; border-bottom:1px solid rgba(255,255,255,0.03);">
                <input type="checkbox" class="edit-campaign-gpm-check" value="${p.id}" ${isChecked ? 'checked' : ''} onchange="updateEditSelectedGpmCount()">
                <i class="fa-solid fa-robot" style="color:var(--accent-gold); font-size:14px;"></i>
                <span style="font-weight:600; color:#fff; flex:1;">${escapeHtml(p.name)}</span>
                <span style="font-size:11px; color:var(--accent-gold);">@${escapeHtml(p.tiktok_username || 'Chưa gắn')}</span>
                <span class="badge ${p.eligible_10k ? 'badge-success' : 'badge-secondary'}" style="font-size:10px;">${(p.followers_count || 0).toLocaleString()} flw</span>
            </label>
        `;
    }).join('');

    updateEditSelectedGpmCount();
}

function updateEditSelectedChannelsCount() {
    const checked = document.querySelectorAll('.edit-campaign-ch-check:checked');
    const badge = document.getElementById('editCampaignSelectedChannelsCount');
    if (badge) badge.textContent = `Đã chọn: ${checked.length} kênh`;
}

function updateEditSelectedGpmCount() {
    const checked = document.querySelectorAll('.edit-campaign-gpm-check:checked');
    const badge = document.getElementById('editCampaignSelectedGpmCount');
    if (badge) badge.textContent = `Đã chọn: ${checked.length} nick`;
}

function selectAllEditCampaignChannels(select) {
    const boxes = document.querySelectorAll('.edit-campaign-ch-check');
    boxes.forEach(b => {
        if (b.closest('label').style.display !== 'none') {
            b.checked = select;
        }
    });
    updateEditSelectedChannelsCount();
}

function selectAllEditCampaignGpm(select) {
    const boxes = document.querySelectorAll('.edit-campaign-gpm-check');
    boxes.forEach(b => {
        if (b.closest('label').style.display !== 'none') {
            b.checked = select;
        }
    });
    updateEditSelectedGpmCount();
}

function filterEditCampaignChannelList(query) {
    const q = (query || '').toLowerCase().trim();
    const items = document.querySelectorAll('#editCampaignChannelsList .multi-select-item');
    items.forEach(item => {
        item.style.display = item.textContent.toLowerCase().includes(q) ? 'flex' : 'none';
    });
}

function filterEditCampaignGpmList(query) {
    const q = (query || '').toLowerCase().trim();
    const items = document.querySelectorAll('#editCampaignGpmList .multi-select-item');
    items.forEach(item => {
        item.style.display = item.textContent.toLowerCase().includes(q) ? 'flex' : 'none';
    });
}

function onEditCampaignFrequencyChange(val) {
    const customWrap = document.getElementById('editCampaignCustomIntervalWrap');
    const daysWrap = document.getElementById('editCampaignDaysOfWeekWrap');
    if (customWrap) customWrap.style.display = val === 'custom_interval' ? 'block' : 'none';
    if (daysWrap) daysWrap.style.display = val === 'specific_days' ? 'block' : 'none';
}

function setEditCampaignSchedulePreset(val) {
    const inp = document.getElementById('editCampaignScheduleInput');
    if (inp) inp.value = val;
}

async function handleEditCampaignSubmit(e) {
    e.preventDefault();
    const campId = document.getElementById('editCampaignId')?.value;
    if (!campId) return;

    const btn = document.getElementById('btnSubmitEditCampaign');

    // Validate Campaign Name
    const campNameInput = document.getElementById('editCampaignNameInput');
    const campName = campNameInput ? campNameInput.value.trim() : '';

    const chBoxes = document.querySelectorAll('.edit-campaign-ch-check:checked');
    const selectedChannelIds = Array.from(chBoxes).map(b => b.value);
    if (selectedChannelIds.length === 0) {
        showToast('⚠️ Vui lòng chọn ít nhất 1 kênh YouTube nguồn!', 'warning');
        return;
    }

    const gpmBoxes = document.querySelectorAll('.edit-campaign-gpm-check:checked');
    const selectedGpmIds = Array.from(gpmBoxes).map(b => parseInt(b.value, 10)).filter(id => !isNaN(id));
    if (selectedGpmIds.length === 0) {
        showToast('⚠️ Vui lòng chọn ít nhất 1 Profile GPMLogin nhận video!', 'warning');
        return;
    }

    // 1. Validate daily_limit
    const dailyLimitInput = document.getElementById('editCampaignDailyLimitInput');
    const rawDailyLimit = parseInt(dailyLimitInput?.value, 10);
    if (isNaN(rawDailyLimit) || rawDailyLimit < 1) {
        markInputError('editCampaignDailyLimitInput', 'Giới hạn video/ngày trên mỗi nick phải là số nguyên >= 1!');
        return;
    }
    const safeDailyLimit = Math.max(1, rawDailyLimit);

    // 2. Validate post_schedule
    const scheduleInput = document.getElementById('editCampaignScheduleInput');
    const scheduleRaw = (scheduleInput?.value || '').trim();
    const rawSlots = scheduleRaw.split(',').map(s => s.trim()).filter(Boolean);
    const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
    const invalidSlot = rawSlots.find(s => !timeRegex.test(s));
    if (!rawSlots.length || invalidSlot) {
        markInputError('editCampaignScheduleInput', `Khung giờ đăng không hợp lệ: "${invalidSlot || 'trống'}". Định dạng chuẩn: HH:MM`);
        return;
    }
    const safeSlots = Array.from(new Set(rawSlots.map(s => {
        const [h, m] = s.split(':');
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    })));
    const cleanScheduleStr = safeSlots.join(', ');

    const freq = document.getElementById('editCampaignFrequencySelect')?.value || 'daily';
    let intervalDays = 1;
    if (freq === 'every_2_days') intervalDays = 2;
    else if (freq === 'every_3_days') intervalDays = 3;
    else if (freq === 'custom_interval') {
        const customIntVal = parseInt(document.getElementById('editCampaignCustomIntervalInput')?.value, 10);
        if (isNaN(customIntVal) || customIntVal < 1 || customIntVal > 365) {
            markInputError('editCampaignCustomIntervalInput', 'Chu kỳ lặp lại phải từ 1 đến 365 ngày!');
            return;
        }
        intervalDays = customIntVal;
    }

    const minDurVal = document.getElementById('editCampaignMinDurationInput')?.value.trim();
    const maxDurVal = document.getElementById('editCampaignMaxDurationInput')?.value.trim();
    if (minDurVal && maxDurVal) {
        const minD = parseInt(minDurVal, 10);
        const maxD = parseInt(maxDurVal, 10);
        if (minD >= maxD) {
            markInputError('editCampaignMinDurationInput', 'Thời lượng tối thiểu phải nhỏ hơn thời lượng tối đa!');
            return;
        }
    }

    const clipsPerVid = parseInt(document.getElementById('editCampaignClipsPerVideoInput')?.value, 10) || 3;
    if (clipsPerVid < 1 || clipsPerVid > 20) {
        markInputError('editCampaignClipsPerVideoInput', 'Số phần cắt mỗi video phải từ 1 đến 20!');
        return;
    }

    const bgmVol = parseFloat(document.getElementById('editCampaignBgmVolume')?.value || 0.15);
    if (isNaN(bgmVol) || bgmVol < 0 || bgmVol > 1) {
        markInputError('editCampaignBgmVolume', 'Âm lượng nhạc nền BGM phải từ 0.0 đến 1.0 (0% - 100%)!');
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Lưu Thay Đổi...';
    }

    const dowBoxes = document.querySelectorAll('.edit-campaign-dow-check:checked');
    const daysOfWeek = Array.from(dowBoxes).map(b => b.value).join(',');
    const randomDelay = parseInt(document.getElementById('editCampaignRandomDelaySelect')?.value, 10) || 10;
    const warmup = document.getElementById('editCampaignWarmupSwitch')?.checked ? 1 : 0;

    const payload = {
        name: campName || `Chiến Dịch Auto`,
        channel_id: selectedChannelIds[0],
        channel_ids: selectedChannelIds,
        gpm_profile_id: selectedGpmIds[0],
        gpm_profile_ids: selectedGpmIds,
        distribution_mode: document.getElementById('editCampaignDistributionMode')?.value || 'round_robin',
        download_dir: document.getElementById('editCampaignDownloadDir')?.value.trim() || 'data/downloads',
        render_dir: document.getElementById('editCampaignRenderDir')?.value.trim() || 'data/rendered',
        aspect_ratio: document.getElementById('editCampaignAspectRatio')?.value || '9:16_blur',
        preset_name: document.getElementById('editCampaignAspectRatio')?.value === '9:16_blur' ? 'TikTok Beta Chuẩn 9:16 (Nền Mờ)' : 'TikTok Chuẩn 9:16',
        video_duration: parseInt(document.getElementById('editCampaignVideoDuration')?.value, 10) || 65,
        min_video_duration: minDurVal ? parseInt(minDurVal, 10) : null,
        max_video_duration: maxDurVal ? parseInt(maxDurVal, 10) : null,
        ai_model: document.getElementById('editCampaignAiModel')?.value || 'default',
        ai_provider: (document.getElementById('editCampaignAiModel')?.value || '').startsWith('gemini') ? 'gemini' : ((document.getElementById('editCampaignAiModel')?.value || '').startsWith('gpt') ? 'openai' : 'deepseek'),
        subtitle_enabled: document.getElementById('editCampaignSubtitleSwitch')?.checked ? 1 : 0,
        subtitle_style: document.getElementById('editCampaignSubtitleStyle')?.value || 'karaoke_yellow',
        add_part_label: document.getElementById('editCampaignAddPartLabelSwitch')?.checked ? 1 : 0,
        clips_per_video: clipsPerVid,
        speed_factor: document.getElementById('editCampaignSpeedSwitch')?.checked ? 1.03 : 1.0,
        flip_horizontal: document.getElementById('editCampaignFlipSwitch')?.checked ? 1 : 0,
        daily_limit: safeDailyLimit,
        post_schedule: cleanScheduleStr,
        post_frequency: freq,
        post_interval_days: intervalDays,
        post_days_of_week: daysOfWeek || 'mon,tue,wed,thu,fri,sat,sun',
        random_delay_minutes: randomDelay,
        min_post_interval_minutes: document.getElementById('editCampaignMinPostIntervalSelect')?.value ? parseInt(document.getElementById('editCampaignMinPostIntervalSelect').value, 10) : null,
        warmup_mode: warmup,
        bgm_folder: document.getElementById('editCampaignBgmSwitch')?.checked ? (document.getElementById('editCampaignBgmFolder')?.value || '') : '',
        bgm_volume: bgmVol,
        is_active: editCampaignOriginalData ? editCampaignOriginalData.is_active : 1
    };

    try {
        const res = await fetch(`/api/campaigns/${campId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast('✅ Đã lưu cập nhật chiến dịch thành công!', 'success');
            closeEditCampaignModal();
            loadCampaigns();
            loadPipelineStatus();
        } else {
            showToast('Lỗi: ' + (data.detail || data.message || 'Không thể cập nhật chiến dịch'), 'error');
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-save"></i> Lưu Thay Đổi Chiến Dịch';
        }
    }
}

// ==========================================
// 9.2 CAMPAIGN LOGS & ACTIVITY MONITOR LOGIC
// ==========================================
let activeLogCampaignId = null;

async function openCampaignLogs(campaignId, campaignName) {
    activeLogCampaignId = campaignId;
    const modal = document.getElementById('campaignLogsModal');
    if (!modal) return;

    const titleEl = document.getElementById('campLogTitle');
    if (titleEl) {
        const displayName = campaignName || `Chiến Dịch #${campaignId}`;
        titleEl.textContent = displayName;
        titleEl.title = displayName;
        titleEl.setAttribute('data-tooltip', displayName);
    }

    modal.classList.add('show');
    modal.classList.add('active');
    await refreshCurrentCampaignLogs();
}

function closeCampaignLogsModal() {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
        document.activeElement.blur();
    }
    const modal = document.getElementById('campaignLogsModal');
    if (modal) {
        modal.classList.remove('show');
        modal.classList.remove('active');
    }
}

async function refreshCurrentCampaignLogs() {
    if (!activeLogCampaignId) return;
    const feedEl = document.getElementById('campaignLogsFeed');
    if (feedEl) feedEl.innerHTML = '<div class="text-muted text-center py-4"><i class="fa-solid fa-spinner fa-spin"></i> Đang cập nhật dữ liệu mới nhất...</div>';

    try {
        const res = await fetch(`/api/campaigns/${activeLogCampaignId}/logs`);
        const data = await res.json();
        if (data.status !== 'success') {
            if (feedEl) feedEl.innerHTML = `<div class="text-danger text-center py-3">Lỗi tải nhật ký: ${escapeHtml(data.detail || 'Không rõ')}</div>`;
            return;
        }

        const camp = data.campaign || {};
        const stats = data.stats || {};
        const logs = data.logs || [];

        // Update Header info
        const titleEl = document.getElementById('campLogTitle');
        if (titleEl) {
            const cName = camp.name || `Chiến Dịch #${activeLogCampaignId}`;
            titleEl.textContent = cName;
            titleEl.title = cName;
            titleEl.setAttribute('data-tooltip', cName);
        }

        const statusBadge = document.getElementById('campLogStatusBadge');
        if (statusBadge) {
            statusBadge.className = `badge ${camp.is_active ? 'badge-success' : 'badge-secondary'}`;
            statusBadge.innerHTML = `<i class="fa-solid fa-circle-dot"></i> ${camp.is_active ? 'Đang Chạy Auto' : 'Tạm Dừng'}`;
        }

        const cadenceBadge = document.getElementById('campLogCadenceBadge');
        if (cadenceBadge) {
            cadenceBadge.innerHTML = `<i class="fa-solid fa-calendar-days"></i> ${camp.post_frequency === 'every_2_days' ? 'Cách 2 ngày' : (camp.post_frequency === 'every_3_days' ? 'Cách 3 ngày' : 'Mỗi ngày')}`;
        }

        // Update 4 Metrics Stats
        const dlEl = document.getElementById('campStatDownloaded');
        if (dlEl) dlEl.textContent = stats.downloaded_videos || 0;

        const totVideosEl = document.getElementById('campStatTotalVideos');
        if (totVideosEl) totVideosEl.textContent = `trong ${stats.total_videos || 0} video phát hiện`;

        const rdEl = document.getElementById('campStatRendered');
        if (rdEl) rdEl.textContent = stats.rendered_videos || 0;

        const qEl = document.getElementById('campStatQueued');
        if (qEl) qEl.textContent = stats.queued_tasks || 0;

        const upEl = document.getElementById('campStatUploaded');
        if (upEl) upEl.textContent = stats.completed_tasks || 0;

        const failEl = document.getElementById('campStatFailed');
        if (failEl) failEl.textContent = `${stats.failed_tasks || 0} lỗi`;

        const countText = document.getElementById('campLogCountText');
        if (countText) countText.textContent = `${logs.length} sự kiện ghi nhận`;

        const vCountBadge = document.getElementById('campVideosCountBadge');
        if (vCountBadge) vCountBadge.textContent = (data.videos || []).length;
        const lCountBadge = document.getElementById('campLogsCountBadge');
        if (lCountBadge) lCountBadge.textContent = logs.length;

        // 1. Render Video Pipeline Flow (Channel -> Downloaded -> Rendered -> TikTok account)
        const vListEl = document.getElementById('campaignVideosList');
        if (vListEl) {
            const vids = data.videos || [];
            if (!vids.length) {
                vListEl.innerHTML = `
                    <div style="text-align:center; padding:32px 20px; background:rgba(255,255,255,0.02); border-radius:10px; border:1px dashed rgba(255,255,255,0.1);">
                        <i class="fa-solid fa-cloud-arrow-down text-cyan" style="font-size:32px; opacity:0.6; margin-bottom:10px; display:block;"></i>
                        <div style="font-size:14px; font-weight:700; color:#fff;">Chưa phát hiện video nào từ các kênh nguồn này</div>
                        <div style="font-size:12px; color:var(--text-muted); margin-top:4px; max-width:480px; margin-left:auto; margin-right:auto;">
                            Hệ thống sẽ tự động quét RSS mỗi 15 phút, tải video MP4 gốc, render dọc 9:16 và phân phối lên dàn nick TikTok GPMLogin theo lịch.
                        </div>
                        <button type="button" class="btn btn-sm btn-accent mt-3" onclick="triggerCampaignTestRun()" style="background:linear-gradient(135deg, #00f2fe 0%, #4facfe 100%); color:#05131e; font-weight:700;">
                            <i class="fa-solid fa-bolt"></i> Bấm Quét & Tải Thử Ngay
                        </button>
                    </div>
                `;
            } else {
                vListEl.innerHTML = vids.map(v => {
                    const dlBadge = v.download_path
                        ? `<span class="badge badge-blue" style="font-size:10.5px;" title="${escapeHtml(v.download_path)}"><i class="fa-solid fa-cloud-arrow-down"></i> Đã tải MP4 gốc</span>`
                        : '<span class="badge badge-secondary" style="font-size:10.5px;"><i class="fa-solid fa-clock"></i> Chờ tải</span>';

                    const rdBadge = v.rendered_path
                        ? `<span class="badge badge-purple" style="font-size:10.5px;" title="${escapeHtml(v.rendered_path)}"><i class="fa-solid fa-wand-magic-sparkles"></i> Đã Render 9:16</span>`
                        : (v.status === 'rendering' ? '<span class="badge badge-purple" style="font-size:10.5px;"><i class="fa-solid fa-spinner fa-spin"></i> Đang render</span>' : '<span class="badge badge-secondary" style="font-size:10.5px;">Chưa render</span>');

                    const tiktokNick = v.tiktok_username || v.gpm_name;
                    const gpmBadge = tiktokNick
                        ? `<span class="badge badge-gold" style="font-size:11px;"><i class="fa-brands fa-tiktok"></i> ${escapeHtml(tiktokNick.startsWith('@') ? tiktokNick : '@' + tiktokNick)}</span>`
                        : '<span class="badge badge-secondary" style="font-size:10.5px;">Đang xếp lịch Round-Robin</span>';

                    let upBadge = '';
                    if (v.upload_status === 'completed') {
                        upBadge = `<span class="badge badge-success" style="font-size:10.5px;"><i class="fa-solid fa-circle-check"></i> Đã đăng (${escapeHtml(v.uploaded_at ? v.uploaded_at.substring(11, 16) : 'xong')})</span>`;
                    } else if (v.upload_status === 'failed') {
                        upBadge = '<span class="badge badge-danger" style="font-size:10.5px;"><i class="fa-solid fa-circle-xmark"></i> Lỗi đăng bài</span>';
                    } else if (v.scheduled_time) {
                        upBadge = `<span class="badge badge-cyan" style="font-size:10.5px;"><i class="fa-regular fa-clock"></i> Giờ hẹn: ${escapeHtml(v.scheduled_time)}</span>`;
                    } else if (v.rendered_path) {
                        upBadge = '<span class="badge badge-warning" style="font-size:10.5px;"><i class="fa-solid fa-hourglass-start"></i> Chờ đến khung giờ đăng</span>';
                    } else {
                        upBadge = '<span class="badge badge-secondary" style="font-size:10.5px;">Chờ render xong</span>';
                    }

                    return `
                        <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:8px; padding:10px 14px; display:flex; align-items:center; justify-content:space-between; gap:14px; flex-wrap:wrap; transition:border-color 0.2s;" onmouseover="this.style.borderColor='rgba(0,242,254,0.3)'" onmouseout="this.style.borderColor='rgba(255,255,255,0.06)'">
                            <div style="flex:1 1 260px; min-width:0; max-width:320px; overflow:hidden;">
                                <div style="display:flex; align-items:center; gap:8px; font-size:11.5px; color:var(--text-muted); margin-bottom:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                                    <span style="color:#ff0000; flex-shrink:0;"><i class="fa-brands fa-youtube"></i></span>
                                    <strong style="color:var(--accent-blue); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(v.channel_name || 'YouTube')}</strong>
                                    <span style="flex-shrink:0;">• ${escapeHtml(v.created_at ? v.created_at.substring(0, 16) : '')}</span>
                                    ${v.duration ? `<span class="badge" style="font-size:10px; background:rgba(255,255,255,0.06); flex-shrink:0;">${v.duration}s</span>` : ''}
                                </div>
                                <h5 class="camp-video-title" style="margin:0; font-size:13px; color:#fff; font-weight:600; line-height:1.4; max-width:320px; width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; display:block;" title="${escapeHtml(v.title || 'Video #' + v.id)}">${escapeHtml(v.title || 'Video #' + v.id)}</h5>
                            </div>
                            <div style="display:flex; flex-direction:column; gap:4px; align-items:flex-start; min-width:130px;">
                                ${dlBadge}
                                ${rdBadge}
                            </div>
                            <div style="display:flex; flex-direction:column; gap:4px; align-items:flex-end; min-width:160px;">
                                <div style="display:flex; align-items:center; gap:6px;">
                                    <span style="font-size:11px; color:var(--text-muted);">Nick nhận:</span>
                                    ${gpmBadge}
                                </div>
                                ${upBadge}
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }

        // 2. Render Activity Logs
        const actionBadges = {
            'scan': '<span class="badge badge-blue" style="font-size:10px;"><i class="fa-solid fa-radar"></i> QUÉT RSS</span>',
            'download': '<span class="badge badge-cyan" style="font-size:10px;"><i class="fa-solid fa-download"></i> TẢI VIDEO</span>',
            'render': '<span class="badge badge-purple" style="font-size:10px;"><i class="fa-solid fa-wand-magic-sparkles"></i> RENDER 9:16</span>',
            'upload': '<span class="badge badge-gold" style="font-size:10px;"><i class="fa-brands fa-tiktok"></i> ĐĂNG BÀI</span>',
            'system': '<span class="badge badge-secondary" style="font-size:10px;"><i class="fa-solid fa-gear"></i> HỆ THỐNG</span>',
            'error': '<span class="badge badge-danger" style="font-size:10px;"><i class="fa-solid fa-circle-exclamation"></i> LỖI</span>'
        };

        const levelColors = {
            'SUCCESS': '#10b981',
            'ERROR': '#ef4444',
            'WARNING': '#f59e0b',
            'INFO': '#00f2fe'
        };

        if (feedEl) {
            if (!logs.length) {
                feedEl.innerHTML = `<div class="text-muted text-center py-5" style="font-size:12px;"><i class="fa-solid fa-clock-rotate-left mb-2" style="font-size:24px; display:block; opacity:0.4;"></i>Chưa có sự kiện nào được ghi nhận cho chiến dịch này.<br><span style="font-size:11px; color:var(--text-muted);">Bấm <strong>"Quét & Chạy Thử Ngay"</strong> để kích hoạt quét và kiểm tra tiến trình!</span></div>`;
            } else {
                feedEl.innerHTML = logs.map(l => {
                    const actBadge = actionBadges[l.action] || actionBadges['system'];
                    const lvlColor = levelColors[l.level] || 'var(--text-secondary)';
                    return `
                        <div style="display:flex; align-items:flex-start; gap:10px; padding:6px 10px; border-bottom:1px solid rgba(255,255,255,0.04); font-size:12px; transition:background 0.15s ease;" onmouseover="this.style.background='rgba(255,255,255,0.02)'" onmouseout="this.style.background='transparent'">
                            <span style="color:var(--text-muted); font-size:11px; white-space:nowrap; padding-top:2px; font-family:monospace;">
                                ${escapeHtml(l.created_at || '')}
                            </span>
                            <div style="flex-shrink:0;">${actBadge}</div>
                            <div style="flex:1; word-break:break-word; color:#e2e8f0; line-height:1.4;">
                                <span style="color:${lvlColor}; font-weight:700; margin-right:4px;">[${escapeHtml(l.level || 'INFO')}]</span>
                                ${escapeHtml(l.message || '')}
                                ${l.details ? `<div style="color:var(--text-muted); font-size:11px; margin-top:3px; font-family:monospace; background:rgba(0,0,0,0.3); padding:3px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.04);">${escapeHtml(l.details)}</div>` : ''}
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }

    } catch (err) {
        if (feedEl) feedEl.innerHTML = `<div class="text-danger text-center py-3">Lỗi kết nối máy chủ: ${escapeHtml(err.message)}</div>`;
    }
}

function switchCampaignDetailTab(tab) {
    const vContainer = document.getElementById('campaignVideosContainer');
    const lContainer = document.getElementById('campaignLogsContainer');
    const vBtn = document.getElementById('btnCampTabVideos');
    const lBtn = document.getElementById('btnCampTabLogs');

    if (tab === 'videos') {
        if (vContainer) vContainer.style.display = 'flex';
        if (lContainer) lContainer.style.display = 'none';
        if (vBtn) { vBtn.className = 'btn btn-sm btn-primary'; }
        if (lBtn) { lBtn.className = 'btn btn-sm btn-secondary'; }
    } else {
        if (vContainer) vContainer.style.display = 'none';
        if (lContainer) lContainer.style.display = 'flex';
        if (vBtn) { vBtn.className = 'btn btn-sm btn-secondary'; }
        if (lBtn) { lBtn.className = 'btn btn-sm btn-primary'; }
    }
}

async function triggerCampaignTestRun() {
    if (!activeLogCampaignId) return;
    const btn = document.getElementById('btnTestRunCampaign');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Kích Hoạt Quét...';
    }
    showToast('⚡ Đang gửi yêu cầu quét và kiểm tra chạy thử cho chiến dịch...');
    try {
        const res = await fetch(`/api/campaigns/${activeLogCampaignId}/test-run`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('✅ ' + data.message);
            setTimeout(refreshCurrentCampaignLogs, 1500);
            setTimeout(refreshCurrentCampaignLogs, 4000);
        } else {
            showToast('Lỗi: ' + (data.detail || 'Không thể chạy quét'), true);
        }
    } catch (err) {
        showToast('Lỗi: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-bolt"></i> Quét & Chạy Thử Ngay';
        }
    }
}

async function triggerDirectCampaignRun(id, name) {
    showToast(`⚡ Đang gửi yêu cầu quét và kiểm tra chạy thử cho chiến dịch '${name}'...`);
    try {
        const res = await fetch(`/api/campaigns/${id}/test-run`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('✅ ' + data.message);
        } else {
            showToast('Lỗi: ' + (data.detail || 'Không thể chạy quét'), true);
        }
    } catch (err) {
        showToast('Lỗi: ' + err.message, true);
    }
}

// ==========================================
// 10. VIDEO STUDIO & RECIPE LOGIC
// ==========================================
let studioSearchQuery = '';
let studioChannelFilter = '';
let studioDisplayLimit = 30;

async function loadStudioVideos() {
    const listEl = document.getElementById('studioVideoList');
    const badge = document.getElementById('studioVideoCountBadge');
    try {
        const res = await fetch('/api/video/list');
        const videos = await res.json();
        cachedVideos = videos;
        if (badge) badge.textContent = `${videos.length} Video`;

        populateStudioChannelFilter();
        if (!currentStudioFilter) currentStudioFilter = 'all';
        document.getElementById('btnFilterAllVideos')?.classList.toggle('active', currentStudioFilter === 'all');
        document.getElementById('btnFilterUnrenderedVideos')?.classList.toggle('active', currentStudioFilter === 'unrendered');
        document.getElementById('btnFilterRenderedVideos')?.classList.toggle('active', currentStudioFilter === 'rendered');
        renderStudioVideoList();

        // If no active video selected, pick the first video
        if (!activeStudioVideo && videos.length > 0) {
            selectStudioVideo(videos[0].yt_video_id || videos[0].id);
        }
    } catch (err) {
        console.error('Lỗi nạp video studio:', err);
    }
}

async function refreshStudioVideos() {
    const icon = document.getElementById('iconRefreshStudio');
    if (icon) icon.classList.add('fa-spin');
    showToast('Đang quét và đồng bộ thư mục video với hệ thống...');
    try {
        const res = await fetch('/api/video/sync', { method: 'POST' });
        const data = await res.json();
        await loadStudioVideos();
        showToast('✅ ' + (data.message || 'Đã làm mới thư viện video'));
    } catch (err) {
        showToast('Lỗi đồng bộ: ' + err.message, true);
    } finally {
        if (icon) {
            setTimeout(() => icon.classList.remove('fa-spin'), 600);
        }
    }
}

function filterStudioVideos(filter) {
    currentStudioFilter = filter;
    studioDisplayLimit = 30;
    document.getElementById('btnFilterAllVideos')?.classList.toggle('active', filter === 'all');
    document.getElementById('btnFilterUnrenderedVideos')?.classList.toggle('active', filter === 'unrendered');
    document.getElementById('btnFilterRenderedVideos')?.classList.toggle('active', filter === 'rendered');
    renderStudioVideoList();
}

function onStudioSearchInput(val) {
    studioSearchQuery = (val || '').toLowerCase().trim();
    studioDisplayLimit = 30;
    renderStudioVideoList();
}

function onStudioChannelFilterChange(val) {
    studioChannelFilter = val || '';
    studioDisplayLimit = 30;
    renderStudioVideoList();
}

function clearStudioFilters() {
    studioSearchQuery = '';
    studioChannelFilter = '';
    studioDisplayLimit = 30;
    const sInput = document.getElementById('studioSearchInput');
    const chSelect = document.getElementById('studioChannelFilterSelect');
    if (sInput) sInput.value = '';
    if (chSelect) chSelect.value = '';
    renderStudioVideoList();
}

function loadMoreStudioVideos() {
    studioDisplayLimit += 30;
    renderStudioVideoList();
}

function populateStudioChannelFilter() {
    const select = document.getElementById('studioChannelFilterSelect');
    if (!select) return;
    const currentVal = select.value;
    const channels = Array.from(new Set(cachedVideos.map(v => v.channel_name).filter(Boolean))).sort();
    let html = '<option value="">Tất cả kênh nguồn (' + cachedVideos.length + ' video)</option>';
    channels.forEach(ch => {
        const count = cachedVideos.filter(v => v.channel_name === ch).length;
        html += `<option value="${escapeHtml(ch)}">${escapeHtml(ch)} (${count})</option>`;
    });
    select.innerHTML = html;
    if (channels.includes(currentVal)) {
        select.value = currentVal;
    }
}

function renderStudioVideoList() {
    const listEl = document.getElementById('studioVideoList');
    const badge = document.getElementById('studioVideoCountBadge');
    if (!listEl) return;

    let filtered = cachedVideos;
    // 1. Lọc theo quy trình: Chưa Render vs Đã Render 9:16
    if (currentStudioFilter === 'unrendered') {
        filtered = filtered.filter(v => !v.has_rendered && v.status !== 'rendered' && (!v.rendered_parts || v.rendered_parts.length === 0));
    } else if (currentStudioFilter === 'rendered') {
        filtered = filtered.filter(v => v.has_rendered || v.status === 'rendered' || (v.rendered_parts && v.rendered_parts.length > 0));
    }

    // 2. Lọc theo kênh nguồn
    if (studioChannelFilter) {
        filtered = filtered.filter(v => (v.channel_name || '').toLowerCase() === studioChannelFilter.toLowerCase());
    }

    // 3. Tìm kiếm tức thì theo từ khóa
    if (studioSearchQuery) {
        filtered = filtered.filter(v => {
            const titleMatch = (v.title || '').toLowerCase().includes(studioSearchQuery);
            const idMatch = (v.yt_video_id || '').toLowerCase().includes(studioSearchQuery) || String(v.id).includes(studioSearchQuery);
            const chMatch = (v.channel_name || '').toLowerCase().includes(studioSearchQuery);
            return titleMatch || idMatch || chMatch;
        });
    }

    // Cập nhật số lượng video hiển thị
    if (badge) {
        if (filtered.length !== cachedVideos.length) {
            badge.textContent = `${filtered.length} / ${cachedVideos.length} Video`;
        } else {
            badge.textContent = `${cachedVideos.length} Video`;
        }
    }

    if (!filtered.length) {
        listEl.innerHTML = `<div class="text-center py-4 text-muted" style="font-size:12px;"><i class="fa-solid fa-magnifying-glass"></i> Không có video phù hợp bộ lọc tìm kiếm.</div>`;
        return;
    }

    const visibleItems = filtered.slice(0, studioDisplayLimit);
    let html = visibleItems.map(v => {
        const isSelected = activeStudioVideo && (activeStudioVideo.id === v.id || activeStudioVideo.yt_video_id === v.yt_video_id);
        const isRendered = v.status === 'rendered' || (v.rendered_parts && v.rendered_parts.length > 0);

        // Hiển thị danh sách các part đã cắt từ video này
        let partsPills = '';
        if (v.rendered_parts && v.rendered_parts.length > 0) {
            partsPills = `
                <div class="svc-parts-container" onclick="event.stopPropagation();">
                    <span style="font-size:11px; color:var(--text-muted); align-self:center; flex-shrink:0;">Parts:</span>
                    ${v.rendered_parts.map(p => `
                        <span class="badge ${activeStudioVideo && activeStudioVideo.id === v.id && activePlaybackType === 'rendered' && activePlaybackPart === p.part ? 'badge-cyan' : 'badge-secondary'}" 
                            style="cursor:pointer; font-size:10.5px; padding:2px 8px; border-radius:4px; flex-shrink:0;" 
                            onclick="selectStudioVideo('${v.yt_video_id || v.id}', 'rendered', ${p.part})"
                            title="Bấm để phát nhanh Part ${p.part}">
                            Part ${p.part}
                        </span>
                    `).join('')}
                </div>
            `;
        }

        const vKey = String(v.yt_video_id || v.id);
        return `
            <div class="studio-video-card ${isSelected ? 'selected' : ''}" onclick="selectStudioVideo('${vKey}')">
                <div class="svc-header">
                    <div class="svc-title" title="${escapeHtml(v.title || '')}">${escapeHtml(v.title || 'Video #' + v.id)}</div>
                    <div class="svc-actions">
                        <button type="button" class="btn-svc-more" onclick="toggleStudioVideoPopover(event, '${vKey}')" title="Tùy chọn video">
                            <i class="fa-solid fa-ellipsis-vertical"></i>
                        </button>
                        <div class="svc-popover" id="svcPopover_${vKey}" onclick="event.stopPropagation()">
                            <button type="button" class="svc-popover-item" onclick="openEditStudioVideoModal('${vKey}')">
                                <i class="fa-solid fa-pen-to-square text-cyan"></i> Chỉnh Sửa Video
                            </button>
                            <button type="button" class="svc-popover-item" onclick="selectStudioVideo('${vKey}')">
                                <i class="fa-solid fa-wand-magic-sparkles text-purple"></i> Mở Biên Tập
                            </button>
                            <button type="button" class="svc-popover-item text-danger" onclick="confirmDeleteStudioVideo('${vKey}')">
                                <i class="fa-solid fa-trash-can"></i> Xóa Video
                            </button>
                        </div>
                    </div>
                </div>
                <div class="svc-meta" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                    <span style="font-size:11.5px; color:var(--text-muted);"><i class="fa-solid fa-clock"></i> ${v.duration || 65}s</span>
                    <span class="badge badge-info" style="font-size:10.5px; padding:3px 8px; max-width:135px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:inline-flex; align-items:center; gap:4px;" title="${escapeHtml(v.channel_name || 'Dán trực tiếp')}">
                        <i class="fa-brands fa-youtube" style="color:#fe2c55; font-size:11px;"></i> ${escapeHtml(v.channel_name || 'Dán trực tiếp')}
                    </span>
                    ${isRendered
                ? `<span class="badge badge-success" style="font-size:10.5px; padding:3px 8px;"><i class="fa-solid fa-check"></i> ${v.rendered_parts && v.rendered_parts.length > 1 ? v.rendered_parts.length + ' Parts' : '9:16'}</span>`
                : '<span class="badge badge-warning" style="font-size:10.5px; padding:3px 8px;">Gốc</span>'}
                </div>
                ${partsPills}
            </div>
        `;
    }).join('');

    // Nút xem thêm nếu danh sách còn video phía sau
    if (filtered.length > studioDisplayLimit) {
        const remaining = filtered.length - studioDisplayLimit;
        html += `
            <button type="button" class="btn btn-secondary btn-sm" onclick="loadMoreStudioVideos()" style="width:100%; margin-top:6px; font-size:11.5px; padding:7px;">
                <i class="fa-solid fa-angles-down"></i> Xem thêm 30 video (còn ${remaining} video)
            </button>
        `;
    }

    listEl.innerHTML = html;
}

function toggleStudioVideoPopover(e, videoKey) {
    if (e) {
        e.stopPropagation();
        e.preventDefault();
    }
    const currentActive = document.querySelector('.svc-popover.active');
    const targetPopover = document.getElementById(`svcPopover_${videoKey}`);
    if (currentActive && currentActive !== targetPopover) {
        currentActive.classList.remove('active');
    }
    if (targetPopover) {
        targetPopover.classList.toggle('active');
    }
}

// Global click dismiss for video card popovers
document.addEventListener('click', (e) => {
    if (!e.target.closest('.svc-actions')) {
        document.querySelectorAll('.svc-popover.active').forEach(p => p.classList.remove('active'));
    }
});

function openEditStudioVideoModal(videoKey) {
    document.querySelectorAll('.svc-popover.active').forEach(p => p.classList.remove('active'));
    const v = cachedVideos.find(item => item.id == videoKey || item.yt_video_id === videoKey);
    if (!v) return;
    const modal = document.getElementById('modalEditStudioVideo');
    const idInput = document.getElementById('editStudioVideoId');
    const titleInput = document.getElementById('editStudioVideoTitle');
    if (idInput) idInput.value = v.yt_video_id || v.id;
    if (titleInput) titleInput.value = v.title || '';
    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('active');
        setTimeout(() => titleInput?.focus(), 100);
    }
}

function closeEditStudioVideoModal() {
    const modal = document.getElementById('modalEditStudioVideo');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('active');
    }
}

async function saveStudioVideoEdit(btn) {
    const idInput = document.getElementById('editStudioVideoId');
    const titleInput = document.getElementById('editStudioVideoTitle');
    const videoKey = idInput?.value;
    const newTitle = titleInput?.value.trim();
    if (!videoKey) return;
    if (!newTitle) {
        markInputError(titleInput, 'Vui lòng nhập tiêu đề cho video!');
        return;
    }

    const orig = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Lưu...';
    }

    try {
        const res = await fetch(`/api/video/${videoKey}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle })
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast('✅ Đã cập nhật tiêu đề video thành công!', 'success');
            closeEditStudioVideoModal();
            // Update in cachedVideos
            const item = cachedVideos.find(v => v.id == videoKey || v.yt_video_id === videoKey);
            if (item) item.title = newTitle;
            if (activeStudioVideo && (activeStudioVideo.id == videoKey || activeStudioVideo.yt_video_id === videoKey)) {
                activeStudioVideo.title = newTitle;
                const titleEl = document.getElementById('studioActiveVideoTitle');
                if (titleEl) titleEl.textContent = newTitle;
            }
            renderStudioVideoList();
        } else {
            showToast('Lỗi cập nhật: ' + (data.detail || data.message || 'Không xác định'), 'error');
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = orig;
        }
    }
}

async function confirmDeleteStudioVideo(videoKey) {
    document.querySelectorAll('.svc-popover.active').forEach(p => p.classList.remove('active'));
    const v = cachedVideos.find(item => item.id == videoKey || item.yt_video_id === videoKey);
    const videoTitle = v ? (v.title || `Video #${v.id}`) : 'video này';

    const confirmed = await showConfirmDialog({
        title: 'Xác Nhận Xóa Video',
        message: `Bạn có chắc muốn xóa video "${videoTitle}"?`,
        details: 'File video gốc và toàn bộ các Part 9:16 đã render trên ổ đĩa sẽ bị xóa vĩnh viễn.',
        confirmText: 'Xác Nhận Xóa',
        confirmClass: 'btn-danger'
    });
    if (!confirmed) return;

    showToast('Đang xóa video và dọn dẹp file...');
    try {
        const res = await fetch(`/api/video/${videoKey}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`✅ ${data.message || 'Đã xóa video thành công!'}`, 'success');
            // Remove from cachedVideos
            cachedVideos = cachedVideos.filter(item => item.id != videoKey && item.yt_video_id !== videoKey);
            if (activeStudioVideo && (activeStudioVideo.id == videoKey || activeStudioVideo.yt_video_id === videoKey)) {
                activeStudioVideo = cachedVideos.length > 0 ? cachedVideos[0] : null;
            }
            populateStudioChannelFilter();
            renderStudioVideoList();
            if (activeStudioVideo) {
                selectStudioVideo(activeStudioVideo.yt_video_id || activeStudioVideo.id);
            }
            // Also refresh other tables if needed
            loadVideos();
            loadDashboardStats();
        } else {
            showToast('Lỗi khi xóa video: ' + (data.detail || data.message || 'Không xác định'), 'error');
        }
    } catch (err) {
        showToast('Lỗi kết nối khi xóa video: ' + err.message, 'error');
    }
}

let activePlaybackType = 'auto'; // 'original' hoặc 'rendered'
let activePlaybackPart = 1;

function selectStudioVideo(videoId, playType = null, partNum = 1) {
    const v = cachedVideos.find(item => item.id == videoId || item.yt_video_id === videoId);
    if (!v) return;
    activeStudioVideo = v;

    if (playType) {
        activePlaybackType = playType;
        activePlaybackPart = partNum;
    } else {
        if (currentStudioFilter === 'unrendered') {
            activePlaybackType = 'original';
            activePlaybackPart = 1;
        } else if (currentStudioFilter === 'rendered') {
            activePlaybackType = 'rendered';
            activePlaybackPart = 1;
        } else {
            activePlaybackType = (v.has_rendered || (v.rendered_parts && v.rendered_parts.length > 0)) ? 'rendered' : 'original';
            activePlaybackPart = 1;
        }
    }

    renderStudioVideoList();

    // Update active video info bar
    const titleEl = document.getElementById('studioActiveVideoTitle');
    const statusEl = document.getElementById('studioMetaStatus');
    const durEl = document.getElementById('studioMetaDuration');
    const chEl = document.getElementById('studioMetaChannel');
    const hiddenId = document.getElementById('studioActiveYtVideoId');

    if (titleEl) titleEl.textContent = v.title || `Video #${v.id}`;
    if (durEl) durEl.textContent = `${v.duration || 65}s`;
    if (chEl) chEl.textContent = v.channel_name || 'Dán trực tiếp';
    if (statusEl) {
        const isRen = v.status === 'rendered' || (v.rendered_parts && v.rendered_parts.length > 0);
        statusEl.textContent = isRen ? 'Đã Render 9:16' : 'Chưa Render';
        statusEl.className = `badge ${isRen ? 'badge-success' : 'badge-warning'}`;
    }
    if (hiddenId) hiddenId.value = v.yt_video_id || v.id;

    // Render Version Switcher Bar (Chỉ hiển thị khi có các Part đã cắt)
    renderStudioVersionsBar(v);

    // Update Phone Mockup Overlay
    const captionEl = document.getElementById('ttOverlayCaption');
    const partBadge = document.getElementById('ttOverlayPartBadge');
    if (captionEl) {
        captionEl.textContent = (v.ai_title || v.title || 'Video ngắn viral TikTok Beta') + ' ' + (v.ai_tags || '#fyp #xuhuong');
    }
    if (partBadge) {
        if (activePlaybackType === 'original') {
            partBadge.textContent = 'VIDEO GỐC';
            partBadge.style.background = 'rgba(234, 179, 8, 0.85)';
        } else {
            partBadge.textContent = `PART ${activePlaybackPart} (9:16)`;
            partBadge.style.background = 'rgba(0, 242, 254, 0.85)';
        }
    }

    // Update Video Player Source
    const player = document.getElementById('studioVideoPlayer');
    const source = document.getElementById('studioVideoSource');
    if (player && source) {
        let playUrl = '';
        if (activePlaybackType === 'original' && v.raw_url) {
            playUrl = v.raw_url;
        } else if (activePlaybackType === 'rendered' && v.rendered_parts && v.rendered_parts.length > 0) {
            const targetPart = v.rendered_parts.find(p => p.part === activePlaybackPart) || v.rendered_parts[0];
            playUrl = targetPart.url;
        } else {
            playUrl = v.media_url || '';
        }

        if (playUrl) {
            source.src = playUrl;
            player.load();
        } else {
            source.src = '';
        }
    }
}

function renderStudioVersionsBar(v) {
    const bar = document.getElementById('studioVideoVersionsBar');
    if (bar) bar.innerHTML = '';
}

function applyStudioPreset(preset) {
    const ratio = document.getElementById('studioAspectRatio');
    const durationRange = document.getElementById('studioDurationRange');
    const durationVal = document.getElementById('studioDurationVal');
    const flip = document.getElementById('studioFlipHorizontal');
    const speed = document.getElementById('studioSpeedFactor');
    const part = document.getElementById('studioAddPartLabel');
    const hook = document.getElementById('studioGenerateAiHook');

    if (preset === 'beta-standard') {
        if (ratio) ratio.value = '9:16_blur';
        if (durationRange) durationRange.value = 65;
        if (durationVal) durationVal.textContent = '65s';
        if (flip) flip.checked = true;
        if (speed) speed.checked = true;
        if (part) part.checked = true;
        if (hook) hook.checked = true;
    } else if (preset === 'shorts-fast') {
        if (ratio) ratio.value = '9:16_crop';
        if (durationRange) durationRange.value = 45;
        if (durationVal) durationVal.textContent = '45s';
        if (flip) flip.checked = true;
        if (speed) speed.checked = true;
        if (part) part.checked = false;
        if (hook) hook.checked = true;
    }
}

function toggleStudioPlayback() {
    const player = document.getElementById('studioVideoPlayer');
    const btn = document.getElementById('btnStudioPlayToggle');
    if (!player) return;
    if (player.paused) {
        player.play().catch(e => console.warn('Autoplay prevented:', e));
        if (btn) btn.innerHTML = '<i class="fa-solid fa-pause"></i> Dừng Video';
    } else {
        player.pause();
        if (btn) btn.innerHTML = '<i class="fa-solid fa-play"></i> Phát Video';
    }
}

function handleCampaignClipsInputChange(mode, val) {
    let num = parseInt(val, 10);
    const input = mode === 'new' 
        ? document.getElementById('campaignClipsPerVideoInput') 
        : document.getElementById('editCampaignClipsPerVideoInput');
    if (input && val !== '' && (isNaN(num) || num < 1)) {
        num = 1;
        input.value = 1;
    }
    if (isNaN(num)) num = 1;

    const switchEl = mode === 'new'
        ? document.getElementById('campaignAddPartLabelSwitch')
        : document.getElementById('editCampaignAddPartLabelSwitch');
    const textEl = mode === 'new'
        ? document.getElementById('campaignAddPartLabelText')
        : document.getElementById('editCampaignAddPartLabelText');
    const wrapEl = mode === 'new'
        ? document.getElementById('campaignAddPartLabelWrap')
        : document.getElementById('editCampaignAddPartLabelWrap');

    if (switchEl) {
        if (num <= 1) {
            switchEl.checked = false;
            switchEl.disabled = true;
            if (wrapEl) {
                wrapEl.style.opacity = '0.5';
                wrapEl.style.cursor = 'not-allowed';
            }
            if (textEl) {
                textEl.innerHTML = '<i class="fa-solid fa-tag text-muted"></i> Đóng dấu chữ PART X (Tự động tắt vì chỉ cắt 1 clip)';
            }
        } else {
            switchEl.disabled = false;
            switchEl.checked = true;
            if (wrapEl) {
                wrapEl.style.opacity = '1';
                wrapEl.style.cursor = 'pointer';
            }
            if (textEl) {
                textEl.innerHTML = '<i class="fa-solid fa-tag text-cyan"></i> Đóng dấu chữ PART X trên video (Hiển thị / Ẩn chữ Part)';
            }
        }
    }
}

function handleStudioClipsPerVideoChange(val) {
    const switchEl = document.getElementById('studioAddPartLabel');
    const textEl = document.getElementById('studioAddPartLabelText');
    const wrapEl = document.getElementById('studioAddPartLabelWrap');
    if (!switchEl) return;
    if (val === '1') {
        switchEl.checked = false;
        switchEl.disabled = true;
        if (wrapEl) {
            wrapEl.style.opacity = '0.5';
            wrapEl.style.cursor = 'not-allowed';
        }
        if (textEl) textEl.textContent = 'Đóng dấu PART X (Tắt vì chỉ 1 clip)';
    } else {
        switchEl.disabled = false;
        switchEl.checked = true;
        if (wrapEl) {
            wrapEl.style.opacity = '1';
            wrapEl.style.cursor = 'pointer';
        }
        if (textEl) textEl.textContent = 'Đóng dấu PART X & Tiến trình';
    }
}

async function renderStudioActiveVideo(btn) {
    if (!activeStudioVideo) {
        showToast('Vui lòng chọn 1 video từ danh sách bên trái trước!', 'warning');
        return;
    }

    const duration = parseInt(document.getElementById('studioDurationRange')?.value) || 65;
    const clipsCount = parseInt(document.getElementById('studioClipsPerVideo')?.value) || 1;
    const flip = document.getElementById('studioFlipHorizontal')?.checked ?? true;
    const speed = document.getElementById('studioSpeedFactor')?.checked ? 1.03 : 1.0;
    const addPart = document.getElementById('studioAddPartLabel')?.checked ?? true;
    const genHook = document.getElementById('studioGenerateAiHook')?.checked ?? true;
    const selectedModel = document.getElementById('studioAiModelSelect')?.value || 'default';
    const enableSub = document.getElementById('studioEnableSubtitles')?.checked ?? true;
    const subStyle = document.getElementById('studioSubtitleStyle')?.value || 'karaoke_yellow';
    const subPos = document.getElementById('studioSubtitlePosition')?.value || 'center';
    const isSmartCurate = document.getElementById('studioSmartCurate')?.checked ?? true;
    const isEnableBgm = document.getElementById('studioEnableBgm')?.checked ?? false;
    const bgmFolder = isEnableBgm ? (document.getElementById('studioBgmFolder')?.value || null) : null;
    const bgmVolume = parseFloat(document.getElementById('studioBgmVolume')?.value || 0.15);

    if (duration < 10 || duration > 3600) {
        markInputError('studioDurationRange', 'Thời lượng render mỗi clip phải từ 10 đến 3600 giây!');
        return;
    }
    if (clipsCount < 1 || clipsCount > 20) {
        markInputError('studioClipsPerVideo', 'Số phần cắt mỗi video phải từ 1 đến 20!');
        return;
    }
    if (isNaN(bgmVolume) || bgmVolume < 0 || bgmVolume > 1) {
        markInputError('studioBgmVolume', 'Âm lượng nhạc nền BGM phải từ 0.0 đến 1.0 (0% - 100%)!');
        return;
    }

    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Render AI 9:16...';
    }

    showToast(`Bắt đầu render AI (Model: ${selectedModel}, Cắt: ${clipsCount} clip, Thời lượng: ${duration}s, Subtitles: ${enableSub ? 'Bật' : 'Tắt'}, BGM: ${bgmFolder || 'Không'})...`);

    try {
        const endpoint = isSmartCurate ? '/api/video/render-smart-ai' : '/api/video/render';
        const payload = isSmartCurate ? {
            video_id: activeStudioVideo.yt_video_id,
            target_duration: duration,
            flip_horizontal: flip,
            speed_factor: speed,
            add_part_label: addPart,
            generate_hook: genHook,
            ai_model: selectedModel !== 'default' ? selectedModel : null,
            enable_subtitles: enableSub,
            subtitle_style: subStyle,
            subtitle_position: subPos,
            clips_count: clipsCount,
            bgm_folder: bgmFolder,
            bgm_volume: bgmVolume
        } : {
            video_id: activeStudioVideo.yt_video_id,
            duration: duration,
            flip_horizontal: flip,
            speed_factor: speed,
            add_part_label: addPart,
            enable_subtitles: enableSub,
            subtitle_style: subStyle,
            subtitle_position: subPos,
            ai_model: selectedModel !== 'default' ? selectedModel : null,
            clips_count: clipsCount,
            bgm_folder: bgmFolder,
            bgm_volume: bgmVolume
        };

        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && (data.status === 'success' || data.rendered_file)) {
            showToast('Render AI 9:16 thành công! Bạn có thể xem thử trên mô phỏng điện thoại.', 'success');
            const currYtId = activeStudioVideo ? activeStudioVideo.yt_video_id : null;
            await loadStudioVideos();
            filterStudioVideos('rendered');
            if (currYtId) {
                selectStudioVideo(currYtId, 'rendered', 1);
            }
            loadDashboardStats();
            loadPipelineStatus();
            if (typeof loadAiUsageStats === 'function') {
                loadAiUsageStats();
            }
        } else {
            showToast('Lỗi render: ' + (data.detail || data.message || 'Không thể render video'), 'error');
        }
    } catch (err) {
        showToast('Lỗi render: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

function openUploadModalForActiveStudioVideo() {
    if (!activeStudioVideo) {
        showToast('Vui lòng chọn video trước!', true);
        return;
    }
    openUploadModal(activeStudioVideo.id);
}

async function triggerManualPipelineScan(btn) {
    await scanAllSavedChannels(btn);
    loadPipelineStatus();
}

function formatNumber(num) {
    if (!num) return '0';
    if (num >= 1000000000) return (num / 1000000000).toFixed(1) + 'B';
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

// ============================================================
// SETTINGS TAB – API Key Management
// ============================================================
async function loadApiKeySettings() {
    try {
        const res = await fetch('/api/settings/keys');
        if (!res.ok) return;
        const data = await res.json();

        // YouTube keys – show one per line
        const ytRaw = data.youtube_api_keys || '';
        const ytLines = ytRaw.split(',').map(k => k.trim()).filter(Boolean).join('\n');
        const ytEl = document.getElementById('settingYoutubeKeys');
        if (ytEl) ytEl.value = ytLines;

        const dsEl = document.getElementById('settingDeepSeekKey');
        if (dsEl) dsEl.value = data.deepseek_api_key || '';

        const gemEl = document.getElementById('settingGeminiKey');
        if (gemEl) gemEl.value = data.gemini_api_key || '';

        const oaiEl = document.getElementById('settingOpenAiKey');
        if (oaiEl) oaiEl.value = data.openai_api_key || '';

        const provEl = document.getElementById('settingAiProvider');
        if (provEl && data.ai_provider) provEl.value = data.ai_provider;

        const dsModelEl = document.getElementById('settingDeepSeekModel');
        if (dsModelEl && data.deepseek_model) dsModelEl.value = data.deepseek_model;

        const gemModelEl = document.getElementById('settingGeminiModel');
        if (gemModelEl && data.gemini_model) gemModelEl.value = data.gemini_model;

        const oaiModelEl = document.getElementById('settingOpenAiModel');
        if (oaiModelEl && data.openai_model) oaiModelEl.value = data.openai_model;

        const whispEl = document.getElementById('settingWhisperModel');
        if (whispEl && data.whisper_model_size) whispEl.value = data.whisper_model_size;

        const subEl = document.getElementById('settingDynamicSubtitles');
        if (subEl && data.enable_dynamic_subtitles !== undefined) subEl.checked = !!data.enable_dynamic_subtitles;

        const subStyleEl = document.getElementById('settingSubtitleStyle');
        if (subStyleEl && data.subtitle_style) subStyleEl.value = data.subtitle_style;

        const subPosEl = document.getElementById('settingSubtitlePosition');
        if (subPosEl && data.subtitle_position) subPosEl.value = data.subtitle_position;

        const subFontEl = document.getElementById('settingSubtitleFontSize');
        if (subFontEl && data.subtitle_font_size) subFontEl.value = String(data.subtitle_font_size);

        const subWrap = document.getElementById('settingSubtitleStyleWrap');
        if (subWrap && subEl) subWrap.style.display = subEl.checked ? 'grid' : 'none';

        const antiEl = document.getElementById('settingAntiDetect');
        if (antiEl && data.enable_anti_detect !== undefined) antiEl.checked = !!data.enable_anti_detect;

        const tgEl = document.getElementById('settingTelegramToken');
        if (tgEl) tgEl.value = data.telegram_bot_token || '';

        const tgChatEl = document.getElementById('settingTelegramChatId');
        if (tgChatEl) tgChatEl.value = data.telegram_chat_id || '';

        const gpmEl = document.getElementById('settingGpmUrl');
        if (gpmEl) gpmEl.value = data.gpm_api_base_url || '';

        // Render key pool status table
        renderKeyPoolTable(data.youtube_key_pool || []);

        // Load Telegram Alert Channels
        loadTelegramChannels();

        // Load cleanup retention settings
        try {
            const cleanRes = await fetch('/api/settings/cleanup');
            const cleanData = await cleanRes.json();
            if (cleanData.status === 'success') {
                const mode = cleanData.retention_mode || '7';
                const radios = document.querySelectorAll('input[name="cleanupRetentionMode"]');
                radios.forEach(r => {
                    r.checked = (r.value === mode);
                });
                const customInput = document.getElementById('inputCleanupCustomDays');
                if (customInput && cleanData.custom_days) {
                    customInput.value = cleanData.custom_days;
                }
            }
        } catch (e) {
            console.error('Lỗi nạp cấu hình dọn dẹp:', e);
        }

        // Load System Tray & Auto-Start settings
        loadSystemTraySettings();

        // Load Download Filter settings (min/max duration)
        loadDownloadFilterSettings();

        // Load AI Usage Tracking & Cost stats
        loadAiUsageStats();
    } catch (err) {
        console.error('loadApiKeySettings error:', err);
    }
}

// ============================================================
// SYSTEM TRAY & AUTO-START SETTINGS
// ============================================================
async function loadSystemTraySettings() {
    try {
        const res = await fetch('/api/settings/system-tray');
        if (!res.ok) return;
        const data = await res.json();
        const autoEl = document.getElementById('settingAutostartToggle');
        const minEl = document.getElementById('settingMinimizeToTrayToggle');
        if (autoEl) autoEl.checked = !!data.autostart;
        if (minEl) minEl.checked = !!data.minimize_to_tray;
    } catch (err) {
        console.error('Lỗi nạp cấu hình System Tray:', err);
    }
}

async function toggleAutostartSetting(checked) {
    try {
        const res = await fetch('/api/settings/system-tray', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ autostart: checked })
        });
        const data = await res.json();
        if (checked) {
            showToast('🚀 Đã BẬT tự khởi động ngầm cùng Windows khi mở máy.');
        } else {
            showToast('Đã TẮT tự khởi động cùng Windows.');
        }
    } catch (err) {
        showToast('Lỗi cập nhật cấu hình khởi động: ' + err.message, true);
    }
}

async function toggleMinimizeToTraySetting(checked) {
    try {
        const res = await fetch('/api/settings/system-tray', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ minimize_to_tray: checked })
        });
        const data = await res.json();
        if (checked) {
            showToast('📌 Đã BẬT thu nhỏ xuống Khay Hệ Thống khi đóng cửa sổ.');
        } else {
            showToast('Đã TẮT thu nhỏ xuống khay (ứng dụng sẽ thoát hẳn khi đóng).');
        }
    } catch (err) {
        showToast('Lỗi cập nhật cấu hình khay hệ thống: ' + err.message, true);
    }
}

// ============================================================
// DOWNLOAD FILTER SETTINGS (GLOBAL DURATION LIMITS)
// ============================================================
async function loadDownloadFilterSettings() {
    try {
        const res = await fetch('/api/settings/download-filter');
        if (!res.ok) return;
        const data = await res.json();
        const minEl = document.getElementById('settingMinVideoDuration');
        const maxEl = document.getElementById('settingMaxVideoDuration');
        if (minEl && data.min_video_duration != null) minEl.value = data.min_video_duration;
        if (maxEl && data.max_video_duration != null) maxEl.value = data.max_video_duration;
    } catch (err) {
        console.error('Lỗi nạp cấu hình bộ lọc video:', err);
    }
}

async function saveDownloadFilterSettings() {
    const minVal = parseInt(document.getElementById('settingMinVideoDuration')?.value || '300', 10);
    const maxVal = parseInt(document.getElementById('settingMaxVideoDuration')?.value || '3600', 10);

    if (isNaN(minVal) || minVal < 0) {
        showToast('⚠️ Thời lượng tối thiểu không hợp lệ!', true);
        return;
    }
    if (isNaN(maxVal) || maxVal <= 0) {
        showToast('⚠️ Thời lượng tối đa không hợp lệ!', true);
        return;
    }
    if (minVal >= maxVal) {
        showToast('⚠️ Thời lượng tối thiểu phải nhỏ hơn thời lượng tối đa!', true);
        return;
    }

    try {
        const res = await fetch('/api/settings/download-filter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                min_video_duration: minVal,
                max_video_duration: maxVal
            })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(`✅ Đã lưu bộ lọc thời lượng video: ${minVal}s - ${maxVal}s`);
        } else {
            showToast('Lỗi lưu bộ lọc: ' + (data.detail || 'Không thể lưu'), true);
        }
    } catch (err) {
        showToast('Lỗi kết nối khi lưu bộ lọc: ' + err.message, true);
    }
}

function renderKeyPoolTable(pool) {
    const wrap = document.getElementById('keyPoolStatus');
    const table = document.getElementById('keyPoolTable');
    if (!wrap || !table) return;
    if (!pool || pool.length === 0) {
        wrap.style.display = 'none';
        return;
    }
    wrap.style.display = 'block';
    const rows = pool.map((k, i) => {
        const status = k.is_active
            ? `<span class="key-badge-active"><i class="fa-solid fa-circle-check"></i> Hoạt Động</span>`
            : `<span class="key-badge-cooldown"><i class="fa-solid fa-clock"></i> Cooldown ${Math.ceil(k.cooldown_remaining_sec / 3600)}h</span>`;
        const current = k.is_current ? `<span class="key-badge-current"><i class="fa-solid fa-bolt"></i> Đang Dùng</span>` : '';
        return `<tr>
            <td style="width:32px; color:var(--text-muted);">${i + 1}</td>
            <td class="key-mono">${escapeHtml(k.key_masked)}</td>
            <td>${status}${current}</td>
            <td style="color:var(--text-muted);">${k.is_active ? '—' : `~${Math.ceil(k.cooldown_remaining_sec / 60)} phút`}</td>
        </tr>`;
    }).join('');
    table.innerHTML = `<table class="key-pool-table">
        <thead><tr><th>#</th><th>API Key</th><th>Trạng Thái</th><th>Còn Lại</th></tr></thead>
        <tbody>${rows}</tbody>
    </table>`;
}

async function saveApiKeySettings(btn) {
    const original = btn ? btn.innerHTML : '';
    const resultEl = document.getElementById('saveKeysResult');
    if (resultEl) resultEl.innerHTML = '';

    const fontSizeInput = document.getElementById('settingSubtitleFontSize');
    const subtitleFontSize = fontSizeInput ? (parseInt(fontSizeInput.value, 10) || 54) : 54;
    if (subtitleFontSize < 12 || subtitleFontSize > 120) {
        markInputError('settingSubtitleFontSize', 'Cỡ chữ phụ đề phải từ 12 đến 120 pt!');
        return;
    }

    const gpmUrlInput = document.getElementById('settingGpmUrl');
    const gpmUrl = gpmUrlInput ? gpmUrlInput.value.trim() : '';
    if (gpmUrl && !/^https?:\/\//i.test(gpmUrl)) {
        markInputError('settingGpmUrl', 'GPM API Base URL phải bắt đầu bằng http:// hoặc https:// (VD: http://127.0.0.1:19995)!');
        return;
    }

    const selRadio = document.querySelector('input[name="cleanupRetentionMode"]:checked');
    const retentionMode = selRadio ? selRadio.value : '7';
    const customDaysInput = document.getElementById('inputCleanupCustomDays');
    const customDays = customDaysInput ? (parseInt(customDaysInput.value, 10) || 7) : 7;
    if (retentionMode === 'custom' && (isNaN(customDays) || customDays < 1 || customDays > 3650)) {
        markInputError('inputCleanupCustomDays', 'Số ngày lưu trữ tùy chỉnh phải từ 1 đến 3650 ngày!');
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Lưu...';
    }

    const ytRaw = (document.getElementById('settingYoutubeKeys')?.value || '');
    // Normalize: join lines as comma-separated
    const ytKeys = ytRaw.split(/[\n,;]+/).map(k => k.trim()).filter(Boolean).join(',');

    const payload = {
        youtube_api_keys: ytKeys,
        deepseek_api_key: document.getElementById('settingDeepSeekKey')?.value || '',
        gemini_api_key: document.getElementById('settingGeminiKey')?.value || '',
        openai_api_key: document.getElementById('settingOpenAiKey')?.value || '',
        ai_provider: document.getElementById('settingAiProvider')?.value || 'deepseek',
        deepseek_model: document.getElementById('settingDeepSeekModel')?.value || 'deepseek-chat',
        gemini_model: document.getElementById('settingGeminiModel')?.value || 'gemini-2.5-flash',
        openai_model: document.getElementById('settingOpenAiModel')?.value || 'gpt-4o-mini',
        whisper_model_size: document.getElementById('settingWhisperModel')?.value || 'base',
        enable_dynamic_subtitles: document.getElementById('settingDynamicSubtitles')?.checked ?? true,
        enable_anti_detect: document.getElementById('settingAntiDetect')?.checked ?? true,
        subtitle_style: document.getElementById('settingSubtitleStyle')?.value || 'karaoke_yellow',
        subtitle_position: document.getElementById('settingSubtitlePosition')?.value || 'center',
        subtitle_font_size: subtitleFontSize,
        telegram_bot_token: document.getElementById('settingTelegramToken')?.value || '',
        telegram_chat_id: document.getElementById('settingTelegramChatId')?.value || '',
        gpm_api_base_url: gpmUrl,
    };

    try {
        const res = await fetch('/api/settings/keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (res.ok && data.status === 'ok') {
            await saveSchedulerSettings(null, false);

            // Save cleanup retention policy
            try {
                await fetch('/api/settings/cleanup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ retention_mode: retentionMode, custom_days: customDays })
                });
            } catch (e) {
                console.error('Lỗi lưu cấu hình dọn dẹp:', e);
            }

            if (resultEl) resultEl.innerHTML = `<span style="color:#34d399;"><i class="fa-solid fa-circle-check"></i> Đã lưu toàn bộ cài đặt & chính sách dọn dẹp! Pool: ${data.pool_size} key</span>`;
            showToast(`✅ Đã lưu cấu hình & cài đặt tự động dọn dẹp thành công!`, 'success');
            await loadApiKeySettings(); // refresh pool status
            loadPipelineStatus();
            loadAiUsageStats();
        } else {
            if (resultEl) resultEl.innerHTML = `<span style="color:#f87171;"><i class="fa-solid fa-circle-xmark"></i> ${escapeHtml(data.detail || data.message || 'Lỗi không xác định')}</span>`;
            showToast('Lỗi khi lưu cài đặt: ' + (data.detail || data.message || 'Không xác định'), 'error');
        }
    } catch (err) {
        if (resultEl) resultEl.innerHTML = `<span style="color:#f87171;"><i class="fa-solid fa-circle-xmark"></i> Lỗi kết nối: ${err.message}</span>`;
        showToast('Lỗi kết nối: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = original;
        }
    }
}

// ============================================================
// AI USAGE & COST MANAGEMENT DASHBOARD
// ============================================================
let cachedAiLogs = [];
let aiFilterDate = '7d';
let aiFilterModel = 'all';
let aiSortField = 'created_at';
let aiSortDirection = 'desc';

function isDateInRange(dateStr, rangeKey) {
    if (!dateStr || rangeKey === 'all') return true;
    const d = new Date(dateStr.replace(' ', 'T'));
    if (isNaN(d.getTime())) return true;
    const now = new Date();

    if (rangeKey === 'today') {
        return d.toDateString() === now.toDateString();
    }
    if (rangeKey === '7d') {
        const diffMs = now.getTime() - d.getTime();
        return diffMs >= 0 && diffMs <= 7 * 86400 * 1000;
    }
    if (rangeKey === '14d') {
        const diffMs = now.getTime() - d.getTime();
        return diffMs >= 0 && diffMs <= 14 * 86400 * 1000;
    }
    if (rangeKey === '30d') {
        const diffMs = now.getTime() - d.getTime();
        return diffMs >= 0 && diffMs <= 30 * 86400 * 1000;
    }
    if (rangeKey === 'wtd') {
        const day = now.getDay();
        const diffToMon = now.getDate() - day + (day === 0 ? -6 : 1);
        const monday = new Date(now);
        monday.setDate(diffToMon);
        monday.setHours(0, 0, 0, 0);
        return d >= monday && d <= now;
    }
    if (rangeKey === 'mtd') {
        const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0);
        return d >= startOfMonth && d <= now;
    }
    return true;
}

function getFilteredAiLogs() {
    let list = [...cachedAiLogs];

    // 1. Filter Date
    if (aiFilterDate !== 'all') {
        list = list.filter(l => isDateInRange(l.created_at, aiFilterDate));
    }

    // 2. Filter Model
    if (aiFilterModel !== 'all') {
        const target = aiFilterModel.toLowerCase();
        list = list.filter(l => {
            const m = (l.model || '').toLowerCase();
            const p = (l.provider || '').toLowerCase();
            return m.includes(target) || p.includes(target);
        });
    }

    // 3. Sort
    list.sort((a, b) => {
        let res = 0;
        if (aiSortField === 'created_at') {
            res = (a.created_at || '').localeCompare(b.created_at || '');
        } else if (aiSortField === 'total_tokens') {
            res = (a.total_tokens || 0) - (b.total_tokens || 0);
        } else if (aiSortField === 'estimated_cost') {
            res = (a.estimated_cost || 0) - (b.estimated_cost || 0);
        } else if (aiSortField === 'duration_ms') {
            res = (a.duration_ms || 0) - (b.duration_ms || 0);
        } else if (aiSortField === 'model') {
            res = (a.model || '').localeCompare(b.model || '');
        } else if (aiSortField === 'task') {
            res = (a.task || '').localeCompare(b.task || '');
        }
        return aiSortDirection === 'asc' ? res : -res;
    });

    return list;
}

function updateAiHeaderSortIcons() {
    const fields = [
        { id: 'th-ai-created_at', field: 'created_at' },
        { id: 'th-ai-model', field: 'model' },
        { id: 'th-ai-task', field: 'task' },
        { id: 'th-ai-total_tokens', field: 'total_tokens' },
        { id: 'th-ai-estimated_cost', field: 'estimated_cost' },
        { id: 'th-ai-duration_ms', field: 'duration_ms' }
    ];

    fields.forEach(item => {
        const th = document.getElementById(item.id);
        if (!th) return;
        const icon = th.querySelector('.sort-icon');
        if (aiSortField === item.field) {
            th.classList.add('sorted-active');
            if (icon) {
                icon.className = aiSortDirection === 'asc'
                    ? 'fa-solid fa-arrow-up-short-wide sort-icon'
                    : 'fa-solid fa-arrow-down-wide-short sort-icon';
            }
        } else {
            th.classList.remove('sorted-active');
            if (icon) icon.className = 'fa-solid fa-sort sort-icon';
        }
    });

    const icon = document.getElementById('aiSortDirIcon');
    const text = document.getElementById('aiSortDirText');
    if (icon) icon.className = aiSortDirection === 'asc' ? 'fa-solid fa-arrow-up-wide-short' : 'fa-solid fa-arrow-down-wide-short';
    if (text) text.textContent = aiSortDirection === 'asc' ? 'Tăng dần' : 'Giảm dần';
}

function handleAiDateFilterChange(val) {
    aiFilterDate = val;
    renderAiLogsTable();
}

function handleAiModelFilterChange(val) {
    aiFilterModel = val;
    renderAiLogsTable();
}

function handleAiSortChange(val) {
    aiSortField = val;
    if (['total_tokens', 'estimated_cost', 'duration_ms', 'created_at'].includes(val)) {
        aiSortDirection = 'desc';
    } else {
        aiSortDirection = 'asc';
    }
    updateAiHeaderSortIcons();
    renderAiLogsTable();
}

function toggleAiSortDirection() {
    aiSortDirection = aiSortDirection === 'asc' ? 'desc' : 'asc';
    updateAiHeaderSortIcons();
    renderAiLogsTable();
}

function handleAiHeaderSort(field) {
    if (aiSortField === field) {
        aiSortDirection = aiSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        aiSortField = field;
        aiSortDirection = (field === 'model' || field === 'task') ? 'asc' : 'desc';
        const sel = document.getElementById('aiSortSelect');
        if (sel) sel.value = field;
    }
    updateAiHeaderSortIcons();
    renderAiLogsTable();
}

function resetAiFilters() {
    aiFilterDate = '7d';
    aiFilterModel = 'all';
    aiSortField = 'created_at';
    aiSortDirection = 'desc';

    const selDate = document.getElementById('aiFilterDateSelect');
    if (selDate) selDate.value = '7d';
    const selModel = document.getElementById('aiFilterModelSelect');
    if (selModel) selModel.value = 'all';
    const selSort = document.getElementById('aiSortSelect');
    if (selSort) selSort.value = 'created_at';

    updateAiHeaderSortIcons();
    renderAiLogsTable();
    showToast('Đã đặt lại toàn bộ bộ lọc nhật ký AI!');
}

function exportAiUsageLogsCsv() {
    const list = getFilteredAiLogs();
    if (!list || !list.length) {
        showToast('Không có dữ liệu nhật ký AI để xuất CSV!', true);
        return;
    }

    const headers = [
        'ID Nhật Ký',
        'Thời Gian',
        'Nhà Cung Cấp (Provider)',
        'Mô Hình AI (Model)',
        'Tác Vụ (Task)',
        'Mã Video (Video ID)',
        'Tổng Tokens Tiêu Thụ',
        'Prompt Tokens',
        'Completion Tokens',
        'Chi Phí Ước Tính (USD)',
        'Chi Phí Quy Đổi VNĐ (25,400đ)',
        'Thời Gian Xử Lý (ms)',
        'Trạng Thái',
        'Thông Báo Lỗi'
    ];

    const rows = [headers];
    list.forEach(l => {
        const costUsd = Number(l.estimated_cost || 0);
        const costVnd = Math.round(costUsd * 25400);
        rows.push([
            l.id || '',
            l.created_at ? l.created_at.replace('T', ' ').slice(0, 19) : '',
            l.provider || '',
            l.model || '',
            l.task || 'general',
            l.video_id || '',
            l.total_tokens || 0,
            l.prompt_tokens || 0,
            l.completion_tokens || 0,
            costUsd.toFixed(6),
            costVnd,
            l.duration_ms || 0,
            l.status === 'success' ? 'Thành công' : 'Lỗi',
            l.error_message || ''
        ]);
    });

    const dateStr = new Date().toISOString().split('T')[0];
    downloadCsv(`nhat_ky_chi_phi_ai_${dateStr}.csv`, rows);
}

function renderAiLogsTable() {
    const list = getFilteredAiLogs();
    const logsCount = document.getElementById('aiLogsCountBadge');
    if (logsCount) {
        if (aiFilterDate !== 'all' || aiFilterModel !== 'all') {
            logsCount.textContent = `${list.length}/${cachedAiLogs.length} sự kiện`;
        } else {
            logsCount.textContent = `${list.length} sự kiện`;
        }
    }

    // Update Header Sort Icons
    updateAiHeaderSortIcons();

    const logsBody = document.getElementById('aiUsageLogsTableBody');
    if (!logsBody) return;

    if (!list.length) {
        const msg = cachedAiLogs.length === 0
            ? 'Chưa có lịch sử gọi AI. Hãy thử render video AI để bắt đầu theo dõi.'
            : 'Không tìm thấy nhật ký AI nào phù hợp với bộ lọc ngày/mô hình đã chọn.';
        logsBody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:24px; color:rgba(255,255,255,0.4);">${msg}</td></tr>`;
        return;
    }

    logsBody.innerHTML = list.map(l => {
        const isSuccess = l.status === 'success';
        const statusBadge = isSuccess
            ? `<span class="badge" style="background:rgba(34,197,94,0.15); color:#22c55e; border:1px solid rgba(34,197,94,0.3); font-size:11px;">Thành công</span>`
            : `<span class="badge" style="background:rgba(239,68,68,0.15); color:#ef4444; border:1px solid rgba(239,68,68,0.3); font-size:11px;" title="${escapeHtml(l.error_message || '')}">Lỗi</span>`;

        const timeStr = l.created_at ? l.created_at.replace('T', ' ').slice(0, 19) : '—';
        const provBadge = `<div class="table-text-truncate" style="max-width:180px;" title="${escapeHtml(l.provider)} (${escapeHtml(l.model)})"><span style="font-weight:600; color:#fff;">${escapeHtml(l.provider)}</span> <span style="color:var(--text-muted); font-size:11px;">${escapeHtml(l.model)}</span></div>`;

        return `<tr>
            <td style="white-space:nowrap; color:var(--text-muted); font-size:11.5px;">${escapeHtml(timeStr)}</td>
            <td>${provBadge}</td>
            <td><span class="badge badge-secondary" style="font-size:10.5px;">${escapeHtml(l.task || 'general')}</span></td>
            <td><div class="table-text-truncate" style="max-width:120px; font-family:monospace; font-size:11px; color:#38bdf8;" title="${escapeHtml(l.video_id || '')}">${escapeHtml(l.video_id || '—')}</div></td>
            <td style="text-align:right; font-weight:600; color:#c084fc;">${(l.total_tokens || 0).toLocaleString()}</td>
            <td style="text-align:right; font-weight:700; color:#22c55e;">$${(l.estimated_cost || 0).toFixed(4)}</td>
            <td style="text-align:right; color:var(--text-muted); font-size:11px;">${l.duration_ms ? l.duration_ms + 'ms' : '—'}</td>
            <td style="text-align:center;">${statusBadge}</td>
        </tr>`;
    }).join('');
}

async function loadAiUsageStats() {
    try {
        const res = await fetch('/api/ai/usage');
        if (!res.ok) return;
        const data = await res.json();
        const stats = data.stats || {};
        const breakdown = data.model_breakdown || [];
        cachedAiLogs = data.recent_logs || [];

        // 4 Thẻ Summary
        const elTotalCalls = document.getElementById('aiStatTotalCalls');
        if (elTotalCalls) elTotalCalls.textContent = (stats.total_calls || 0).toLocaleString();

        const elTodayCalls = document.getElementById('aiStatTodayCalls');
        if (elTodayCalls) elTodayCalls.textContent = `Hôm nay: ${(stats.today_calls || 0).toLocaleString()} lượt gọi`;

        const elTotalTokens = document.getElementById('aiStatTotalTokens');
        if (elTotalTokens) elTotalTokens.textContent = (stats.total_tokens || 0).toLocaleString();

        const elTodayTokens = document.getElementById('aiStatTodayTokens');
        if (elTodayTokens) elTodayTokens.textContent = `Hôm nay: ${(stats.today_tokens || 0).toLocaleString()} tokens`;

        const elCostUsd = document.getElementById('aiStatTotalCostUsd');
        if (elCostUsd) elCostUsd.textContent = `$${(stats.total_cost_usd || 0).toFixed(4)}`;

        const elCostVnd = document.getElementById('aiStatTotalCostVnd');
        if (elCostVnd) elCostVnd.textContent = `~ ${(stats.total_cost_vnd || 0).toLocaleString()} VNĐ`;

        const elActiveModel = document.getElementById('aiStatActiveModel');
        if (elActiveModel) {
            const prov = (stats.active_provider || 'deepseek').toUpperCase();
            const mod = stats.active_model || 'deepseek-chat';
            elActiveModel.textContent = `${prov} (${mod})`;
        }

        // Bảng Phân Bổ Theo Từng Mô Hình
        const bdBody = document.getElementById('aiModelBreakdownTableBody');
        if (bdBody) {
            if (!breakdown.length) {
                bdBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:18px; color:var(--text-muted);">Chưa có dữ liệu phân bổ. Khi render video AI, hệ thống sẽ tự động tổng hợp.</td></tr>`;
            } else {
                bdBody.innerHTML = breakdown.map(item => {
                    const provColor = (item.provider || '').toLowerCase().includes('deepseek') ? '#0070f3' :
                        (item.provider || '').toLowerCase().includes('gemini') ? '#10b981' :
                            (item.provider || '').toLowerCase().includes('openai') ? '#10a37f' : '#eab308';
                    return `<tr>
                        <td style="font-weight:600;">
                            <div class="table-text-truncate" style="max-width:200px;" title="${escapeHtml(item.provider)} (${escapeHtml(item.model)})">
                                <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${provColor}; margin-right:6px;"></span>
                                ${escapeHtml(item.provider)} <span style="color:var(--text-muted); font-size:11px;">(${escapeHtml(item.model)})</span>
                            </div>
                        </td>
                        <td style="color:var(--text-secondary); font-size:11.5px;">Phân tích Hook & Viral Curation</td>
                        <td style="text-align:right; font-weight:700;">${(item.calls || 0).toLocaleString()}</td>
                        <td style="text-align:right; color:#a855f7;">${(item.total_tokens || 0).toLocaleString()}</td>
                        <td style="text-align:right; color:var(--text-muted);">${item.avg_duration_ms ? (item.avg_duration_ms / 1000).toFixed(2) + 's' : '—'}</td>
                        <td style="text-align:right; font-weight:700; color:#22c55e;">$${(item.cost_usd || 0).toFixed(4)}</td>
                        <td style="text-align:right; color:#22c55e;">~ ${(item.cost_vnd || 0).toLocaleString()}đ</td>
                    </tr>`;
                }).join('');
            }
        }

        // Bảng Nhật Ký Lượt Gọi Gần Nhất (áp dụng filter và sort)
        renderAiLogsTable();
    } catch (e) {
        console.error('Lỗi nạp thống kê AI usage:', e);
    }
}

async function clearAiUsageStats() {
    const ok = await showConfirmDialog({
        title: 'Làm Sạch Lịch Sử AI',
        message: 'Bạn có chắc chắn muốn xóa toàn bộ lịch sử và nhật ký gọi AI?',
        details: 'Số liệu thống kê token và chi phí sẽ được đặt lại về 0.',
        confirmText: 'Xóa Lịch Sử',
        confirmClass: 'btn-danger'
    });
    if (!ok) return;
    try {
        const res = await fetch('/api/ai/usage/clear', { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.status === 'ok') {
            showToast('✅ Đã xóa sạch lịch sử và đặt lại thống kê AI!');
            await loadAiUsageStats();
        } else {
            showToast('Lỗi xóa lịch sử AI: ' + (data.message || 'Không xác định'), true);
        }
    } catch (e) {
        showToast('Lỗi kết nối khi xóa: ' + e.message, true);
    }
}

async function triggerManualCleanup(btn) {
    const original = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Dọn Dẹp...';
    }
    const statusEl = document.getElementById('manualCleanupStatus');
    if (statusEl) statusEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang kiểm tra file đã đăng...';

    try {
        const selRadio = document.querySelector('input[name="cleanupRetentionMode"]:checked');
        const retentionMode = selRadio ? selRadio.value : null;
        const customDays = parseInt(document.getElementById('inputCleanupCustomDays')?.value) || null;

        const res = await fetch('/api/pipeline/cleanup-uploaded', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: retentionMode, custom_days: customDays })
        });
        const data = await res.json();

        if (data.status === 'success') {
            const msg = data.files_deleted > 0
                ? `Đã giải phóng ${data.mb_freed} MB (${data.files_deleted} file mp4) từ ${data.cleaned_videos} video đã đăng!`
                : `Không có file video nào cần dọn dẹp (tất cả video đã đăng đều nằm trong thời hạn lưu trữ hoặc đã được dọn).`;

            if (statusEl) {
                statusEl.innerHTML = `<span style="color:#10b981;"><i class="fa-solid fa-circle-check"></i> ${escapeHtml(msg)}</span>`;
            }
            showToast(data.files_deleted > 0 ? `🧹 ${msg}` : msg, data.files_deleted > 0 ? 'success' : 'info');
            loadPipelineStatus();
        } else {
            if (statusEl) statusEl.innerHTML = `<span style="color:#ef4444;"><i class="fa-solid fa-circle-xmark"></i> ${escapeHtml(data.message || 'Lỗi dọn dẹp')}</span>`;
            showToast('Lỗi dọn dẹp: ' + (data.message || 'Thất bại'), 'error');
        }
    } catch (err) {
        if (statusEl) statusEl.innerHTML = `<span style="color:#ef4444;">Lỗi kết nối: ${err.message}</span>`;
        showToast('Lỗi kết nối dọn dẹp: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = original;
        }
    }
}

async function testYoutubeKey(btn) {
    const rawKeys = document.getElementById('settingYoutubeKeys')?.value || '';
    const firstKey = rawKeys.split(/[\n,;]+/).map(k => k.trim()).filter(Boolean)[0];
    if (!firstKey) {
        showToast('⚠️ Chưa nhập API Key nào để test.', 'warning');
        return;
    }
    const resultEl = document.getElementById('testKeyResult');
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Test...';
    if (resultEl) resultEl.innerHTML = '';

    try {
        const res = await fetch('/api/settings/test-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: firstKey }),
        });
        const data = await res.json();
        if (data.valid) {
            if (resultEl) resultEl.innerHTML = `<span style="color:#34d399;"><i class="fa-solid fa-circle-check"></i> ${escapeHtml(data.message)}</span>`;
        } else {
            if (resultEl) resultEl.innerHTML = `<span style="color:#f87171;"><i class="fa-solid fa-circle-xmark"></i> ${escapeHtml(data.message)}</span>`;
        }
    } catch (err) {
        if (resultEl) resultEl.innerHTML = `<span style="color:#f87171;">Lỗi: ${err.message}</span>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = original;
    }
}



// ============================================================
// ADVANCED SCHEDULER & AUTO-SCAN SETTINGS
// ============================================================
function openSchedulerSettingsModal() {
    loadSchedulerSettings();
    const modal = document.getElementById('schedulerSettingsModal');
    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('active');
    }
}

function closeSchedulerSettingsModal() {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
        document.activeElement.blur();
    }
    const modal = document.getElementById('schedulerSettingsModal');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('active');
    }
}

// Backdrop click close for schedulerSettingsModal
document.addEventListener('DOMContentLoaded', () => {
    const schedModal = document.getElementById('schedulerSettingsModal');
    if (schedModal) {
        schedModal.addEventListener('click', (e) => {
            if (e.target === schedModal) {
                closeSchedulerSettingsModal();
            }
        });
    }
});

function updateModalIntervalBadge(val) {
    const badge = document.getElementById('modalIntervalBadge');
    if (badge) {
        const num = parseInt(val) || 15;
        badge.textContent = `${num} phút/lần`;
    }
}

function setSchedulerPreset(minutes, isModal) {
    if (isModal) {
        const inp = document.getElementById('modalSchedulerInterval');
        if (inp) {
            inp.value = minutes;
            updateModalIntervalBadge(minutes);
        }
    } else {
        const inp = document.getElementById('settingSchedulerInterval');
        if (inp) inp.value = minutes;
    }
}

async function loadSchedulerSettings() {
    try {
        const res = await fetch('/api/settings/scheduler');
        if (!res.ok) return;
        const data = await res.json();
        const interval = data.interval_minutes || 15;
        const uploadSec = data.upload_interval_seconds || 60;
        const maxVids = data.max_videos_per_scan || 5;
        const delaySec = data.channel_delay_seconds !== undefined ? data.channel_delay_seconds : 2;
        const autoDl = data.auto_download !== undefined ? data.auto_download : true;
        const autoRd = data.auto_render !== undefined ? data.auto_render : true;
        const saveByFolder = data.save_by_channel_folder !== undefined ? data.save_by_channel_folder : false;
        const autoRetry = data.auto_retry_enabled !== undefined ? data.auto_retry_enabled : true;
        const maxRetries = data.max_retries || 2;
        const retryDelay = data.retry_delay_minutes || 15;
        const watchdog = data.watchdog_enabled !== undefined ? data.watchdog_enabled : true;
        const stuckTimeout = data.stuck_timeout_minutes || 15;
        const minCooldown = data.min_account_cooldown_minutes || 60;

        // Populate Modal Fields
        const mInterval = document.getElementById('modalSchedulerInterval');
        if (mInterval) {
            mInterval.value = interval;
            updateModalIntervalBadge(interval);
        }
        const mUpload = document.getElementById('modalUploadInterval');
        if (mUpload) mUpload.value = uploadSec;
        const mMax = document.getElementById('modalMaxVideosPerScan');
        if (mMax) mMax.value = maxVids;
        const mDelay = document.getElementById('modalChannelDelay');
        if (mDelay) mDelay.value = delaySec;
        const mMinCooldown = document.getElementById('modalMinAccountCooldown');
        if (mMinCooldown) mMinCooldown.value = minCooldown;
        const mAutoDl = document.getElementById('modalAutoDownloadToggle');
        if (mAutoDl) mAutoDl.checked = autoDl;
        const mAutoRd = document.getElementById('modalAutoRenderToggle');
        if (mAutoRd) mAutoRd.checked = autoRd;
        const mSaveByFolder = document.getElementById('modalSaveByChannelFolderToggle');
        if (mSaveByFolder) mSaveByFolder.checked = saveByFolder;
        const mAutoRetry = document.getElementById('modalAutoRetryToggle');
        if (mAutoRetry) mAutoRetry.checked = autoRetry;
        const mMaxRetries = document.getElementById('modalMaxRetries');
        if (mMaxRetries) mMaxRetries.value = maxRetries;
        const mRetryDelay = document.getElementById('modalRetryDelay');
        if (mRetryDelay) mRetryDelay.value = retryDelay;
        const mWatchdog = document.getElementById('modalWatchdogToggle');
        if (mWatchdog) mWatchdog.checked = watchdog;
        const mStuckTimeout = document.getElementById('modalStuckTimeout');
        if (mStuckTimeout) mStuckTimeout.value = stuckTimeout;

        // Populate Settings Tab Fields
        const sInterval = document.getElementById('settingSchedulerInterval');
        if (sInterval) sInterval.value = interval;
        const sUpload = document.getElementById('settingUploadInterval');
        if (sUpload) sUpload.value = uploadSec;
        const sMax = document.getElementById('settingMaxVideosPerScan');
        if (sMax) sMax.value = maxVids;
        const sDelay = document.getElementById('settingChannelDelay');
        if (sDelay) sDelay.value = delaySec;
        const sMinCooldown = document.getElementById('settingMinAccountCooldown');
        if (sMinCooldown) sMinCooldown.value = minCooldown;
        const sAutoDl = document.getElementById('settingAutoDownloadToggle');
        if (sAutoDl) sAutoDl.checked = autoDl;
        const sAutoRd = document.getElementById('settingAutoRenderToggle');
        if (sAutoRd) sAutoRd.checked = autoRd;
        const sSaveByFolder = document.getElementById('settingSaveByChannelFolderToggle');
        if (sSaveByFolder) sSaveByFolder.checked = saveByFolder;
    } catch (err) {
        console.error('loadSchedulerSettings error:', err);
    }
}

async function saveSchedulerSettings(btn, fromModal = true) {
    const original = btn ? btn.innerHTML : '';

    let intervalInput, uploadInput, maxVidsInput, delayInput, autoDl, autoRd, saveByFolder;
    let autoRetry = true, maxRetries = 2, retryDelay = 15, watchdog = true, stuckTimeout = 15, minAccountCooldown = 60;

    if (fromModal) {
        intervalInput = document.getElementById('modalSchedulerInterval');
        uploadInput = document.getElementById('modalUploadInterval');
        maxVidsInput = document.getElementById('modalMaxVideosPerScan');
        delayInput = document.getElementById('modalChannelDelay');
        autoDl = document.getElementById('modalAutoDownloadToggle')?.checked ?? true;
        autoRd = document.getElementById('modalAutoRenderToggle')?.checked ?? true;
        saveByFolder = document.getElementById('modalSaveByChannelFolderToggle')?.checked ?? false;
        autoRetry = document.getElementById('modalAutoRetryToggle')?.checked ?? true;
        maxRetries = parseInt(document.getElementById('modalMaxRetries')?.value, 10) || 2;
        retryDelay = parseInt(document.getElementById('modalRetryDelay')?.value, 10) || 15;
        watchdog = document.getElementById('modalWatchdogToggle')?.checked ?? true;
        stuckTimeout = parseInt(document.getElementById('modalStuckTimeout')?.value, 10) || 15;
        minAccountCooldown = parseInt(document.getElementById('modalMinAccountCooldown')?.value, 10) || 60;
    } else {
        intervalInput = document.getElementById('settingSchedulerInterval');
        uploadInput = document.getElementById('settingUploadInterval');
        maxVidsInput = document.getElementById('settingMaxVideosPerScan');
        delayInput = document.getElementById('settingChannelDelay');
        autoDl = document.getElementById('settingAutoDownloadToggle')?.checked ?? true;
        autoRd = document.getElementById('settingAutoRenderToggle')?.checked ?? true;
        saveByFolder = document.getElementById('settingSaveByChannelFolderToggle')?.checked ?? false;
        autoRetry = document.getElementById('modalAutoRetryToggle')?.checked ?? true;
        maxRetries = parseInt(document.getElementById('modalMaxRetries')?.value, 10) || 2;
        retryDelay = parseInt(document.getElementById('modalRetryDelay')?.value, 10) || 15;
        watchdog = document.getElementById('modalWatchdogToggle')?.checked ?? true;
        stuckTimeout = parseInt(document.getElementById('modalStuckTimeout')?.value, 10) || 15;
        minAccountCooldown = parseInt(document.getElementById('settingMinAccountCooldown')?.value, 10) || 60;
    }

    const interval = parseInt(intervalInput?.value, 10);
    const uploadSec = parseInt(uploadInput?.value, 10);
    const maxVids = parseInt(maxVidsInput?.value, 10);
    const delaySec = parseInt(delayInput?.value, 10);

    if (isNaN(interval) || interval < 1 || interval > 1440) {
        markInputError(intervalInput, 'Chu kỳ quét ngầm phải từ 1 đến 1440 phút (tối đa 24 giờ)!');
        return;
    }
    if (isNaN(uploadSec) || uploadSec < 10 || uploadSec > 86400) {
        markInputError(uploadInput, 'Khoảng cách giữa các lần đăng phải từ 10 đến 86400 giây!');
        return;
    }
    if (isNaN(maxVids) || maxVids < 1 || maxVids > 50) {
        markInputError(maxVidsInput, 'Số video quét tối đa mỗi lần phải từ 1 đến 50!');
        return;
    }
    if (isNaN(delaySec) || delaySec < 0 || delaySec > 3600) {
        markInputError(delayInput, 'Độ trễ giữa các kênh phải từ 0 đến 3600 giây!');
        return;
    }
    if (isNaN(minAccountCooldown) || minAccountCooldown < 15 || minAccountCooldown > 1440) {
        showToast('Giãn cách an toàn giữa 2 lần đăng cùng nick phải từ 15 đến 1440 phút!', 'error');
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Lưu...';
    }

    const payload = {
        interval_minutes: interval,
        upload_interval_seconds: uploadSec,
        max_videos_per_scan: maxVids,
        channel_delay_seconds: delaySec,
        auto_download: autoDl,
        auto_render: autoRd,
        save_by_channel_folder: saveByFolder,
        auto_retry_enabled: autoRetry,
        max_retries: maxRetries,
        retry_delay_minutes: retryDelay,
        watchdog_enabled: watchdog,
        stuck_timeout_minutes: stuckTimeout,
        min_account_cooldown_minutes: minAccountCooldown
    };

    try {
        const res = await fetch('/api/settings/scheduler', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`✅ ${data.message || 'Đã lưu cấu hình tự động quét thành công!'}`, 'success');
            if (fromModal) {
                closeSchedulerSettingsModal();
            }
            // Sync values to both modal and tab
            await loadSchedulerSettings();
            // Refresh pipeline banner status immediately
            loadPipelineStatus();
        } else {
            showToast('Lỗi khi lưu cấu hình scheduler: ' + (data.detail || data.message || 'Không xác định'), 'error');
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = original;
        }
    }
}

// ============================================================
// TELEGRAM ALERT CHANNELS MANAGEMENT
// ============================================================

async function loadTelegramChannels() {
    const listEl = document.getElementById('telegramChannelsList');
    const badgeEl = document.getElementById('teleActiveBadge');
    const countTextEl = document.getElementById('teleActiveCountText');
    const totalCountEl = document.getElementById('teleChannelsTotalCount');

    try {
        const res = await fetch('/api/telegram/channels');
        if (!res.ok) throw new Error('Không thể tải danh sách kênh');
        const data = await res.json();
        const channels = data.channels || [];
        const activeCount = channels.filter(c => c.is_active).length;

        if (totalCountEl) totalCountEl.textContent = channels.length;
        if (countTextEl) countTextEl.textContent = `${activeCount} Kênh Đang Bật`;
        if (badgeEl) {
            if (activeCount > 0) {
                badgeEl.style.background = 'rgba(16,185,129,0.15)';
                badgeEl.style.color = '#10b981';
                badgeEl.style.borderColor = 'rgba(16,185,129,0.3)';
            } else {
                badgeEl.style.background = 'rgba(239,68,68,0.15)';
                badgeEl.style.color = '#ef4444';
                badgeEl.style.borderColor = 'rgba(239,68,68,0.3)';
            }
        }

        if (!listEl) return;

        if (channels.length === 0) {
            listEl.innerHTML = `
                <div style="background:rgba(255,255,255,0.02); border:1px dashed var(--border-color); border-radius:var(--radius-md); padding:28px 20px; text-align:center;">
                    <div style="font-size:32px; color:#2AABEE; margin-bottom:8px;"><i class="fa-brands fa-telegram"></i></div>
                    <div style="font-weight:700; font-size:14px; margin-bottom:4px; color:var(--text-primary);">Chưa có kênh Telegram nào</div>
                    <div style="font-size:12px; color:var(--text-muted); max-width:440px; margin:0 auto 16px auto;">
                        Thêm ít nhất một kênh hoặc nhóm Telegram để hệ thống tự động gửi thông báo khi tài khoản TikTok đạt mốc 10.000 Follower.
                    </div>
                    <button type="button" class="btn btn-primary btn-sm" onclick="openAddTelegramChannelModal()">
                        <i class="fa-solid fa-plus"></i> Thêm Kênh Đầu Tiên
                    </button>
                </div>
            `;
            return;
        }

        listEl.innerHTML = channels.map(ch => {
            const isActive = !!ch.is_active;
            const statusLabel = isActive ? 'Đang Bật' : 'Đã Tắt';
            const statusColor = isActive ? '#10b981' : 'var(--text-muted)';
            const escapedName = escapeHtml(ch.name);
            const escapedChatId = escapeHtml(ch.chat_id);
            const chJsonStr = JSON.stringify(ch).replace(/"/g, '&quot;');

            let typeBadges = [];
            if (ch.notify_10k !== 0) {
                typeBadges.push(`<span class="tele-type-badge tele-type-10k" title="Nhận cảnh báo khi nick đạt 10.000 Follower"><i class="fa-solid fa-star"></i> 10K Follower</span>`);
            }
            if (ch.notify_issues !== 0) {
                typeBadges.push(`<span class="tele-type-badge tele-type-issues" title="Nhận cảnh báo lỗi nghiêm trọng & cách khắc phục"><i class="fa-solid fa-triangle-exclamation"></i> Báo Lỗi</span>`);
            }
            if (ch.notify_daily_report !== 0) {
                const rTime = ch.daily_report_time || '21:00';
                typeBadges.push(`<span class="tele-type-badge tele-type-report" title="Nhận báo cáo hoạt động tổng kết hàng ngày lúc ${rTime}"><i class="fa-solid fa-chart-pie"></i> Báo Cáo (${rTime})</span>`);
            }
            if (typeBadges.length === 0) {
                typeBadges.push(`<span class="badge" style="background:rgba(255,255,255,0.05); color:var(--text-muted); font-size:10px;">Chưa chọn loại tin</span>`);
            }

            return `
                <div class="tele-channel-card ${isActive ? '' : 'inactive'}" id="teleChannelRow_${ch.id}">
                    <div class="tele-channel-info">
                        <label class="tele-toggle-switch" title="${isActive ? 'Nhấn để Tắt kênh này' : 'Nhấn để Bật kênh này'}">
                            <input type="checkbox" ${isActive ? 'checked' : ''} onchange="toggleTelegramChannel(${ch.id}, this)">
                            <span class="tele-toggle-slider"></span>
                        </label>
                        <div class="tele-channel-icon">
                            <i class="fa-solid fa-tower-broadcast"></i>
                        </div>
                        <div class="tele-channel-details">
                            <div class="tele-channel-title">
                                <span>${escapedName}</span>
                                <span style="font-size:10.5px; font-weight:600; padding:2px 8px; border-radius:12px; background:${isActive ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.06)'}; color:${statusColor};">
                                    ${statusLabel}
                                </span>
                            </div>
                            <div class="tele-channel-meta">
                                <span><i class="fa-solid fa-id-badge" style="color:var(--text-muted);"></i> Chat ID: <code class="tele-chat-id-badge">${escapedChatId}</code></span>
                                <div style="display:inline-flex; gap:5px; flex-wrap:wrap; margin-left:4px;">
                                    ${typeBadges.join('')}
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="tele-channel-actions">
                        <div class="tele-dropdown-wrap dropdown" style="display:inline-flex; align-items:center; position:relative;">
                            <button type="button" class="btn btn-secondary btn-xs" id="btnTestTele_${ch.id}" onclick="toggleChannelTestMenu(${ch.id}, event)" title="Menu kiểm tra gửi tin tới kênh này">
                                <i class="fa-solid fa-paper-plane"></i> Test <i class="fa-solid fa-caret-down" style="font-size:9px;"></i>
                            </button>
                            <div id="teleTestMenu_${ch.id}" class="tele-test-dropdown" onclick="event.stopPropagation()">
                                <button type="button" class="tele-test-dropdown-item" onclick="testTelegramChannelMode(${ch.id}, 'connection', event)">
                                    <i class="fa-solid fa-plug text-cyan"></i> <span>Test Kết Nối</span>
                                </button>
                                <button type="button" class="tele-test-dropdown-item" onclick="testTelegramChannelMode(${ch.id}, '10k', event)">
                                    <i class="fa-solid fa-star" style="color:#2AABEE;"></i> <span>Test Cảnh Báo 10K</span>
                                </button>
                                <button type="button" class="tele-test-dropdown-item" onclick="testTelegramChannelMode(${ch.id}, 'issue', event)">
                                    <i class="fa-solid fa-triangle-exclamation" style="color:#f59e0b;"></i> <span>Test Báo Lỗi + Fix</span>
                                </button>
                                <button type="button" class="tele-test-dropdown-item" onclick="testTelegramChannelMode(${ch.id}, 'daily_report', event)">
                                    <i class="fa-solid fa-chart-pie" style="color:#10b981;"></i> <span>Test Báo Cáo Ngày</span>
                                </button>
                            </div>
                        </div>
                        <button type="button" class="btn btn-secondary btn-xs has-tooltip tooltip-left"
                            onclick="openEditTelegramChannelModal(${chJsonStr})"
                            data-tooltip="Chỉnh sửa thông tin và loại tin nhận">
                            <i class="fa-solid fa-pen"></i> Sửa
                        </button>
                        <button type="button" class="btn btn-danger btn-xs has-tooltip tooltip-left"
                            onclick="deleteTelegramChannel(${ch.id}, '${escapedName}')"
                            data-tooltip="Xóa kênh này khỏi danh sách">
                            <i class="fa-solid fa-trash-can"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');

    } catch (err) {
        console.error('loadTelegramChannels error:', err);
        if (listEl) {
            listEl.innerHTML = `<div style="color:#ef4444; font-size:12px; padding:12px;"><i class="fa-solid fa-circle-exclamation"></i> Lỗi nạp danh sách kênh Telegram: ${err.message}</div>`;
        }
    }
}

function toggleDailyTimeRow(checked) {
    const row = document.getElementById('teleDailyTimeRow');
    if (row) {
        row.style.display = checked ? 'flex' : 'none';
    }
}

function toggleChannelTestMenu(channelId, e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }
    const currentMenu = document.getElementById(`teleTestMenu_${channelId}`);
    const isShown = currentMenu && currentMenu.classList.contains('show');

    // Đóng tất cả menu test khác
    document.querySelectorAll('.tele-test-dropdown').forEach(el => {
        el.classList.remove('show');
    });

    if (currentMenu && !isShown) {
        currentMenu.classList.add('show');
    }
}

// Lắng nghe click bên ngoài để đóng test menu
document.addEventListener('click', (e) => {
    if (!e.target.closest('.dropdown')) {
        document.querySelectorAll('.tele-test-dropdown').forEach(el => {
            el.classList.remove('show');
        });
    }
});

async function toggleTelegramChannel(channelId, checkboxEl) {
    try {
        const res = await fetch(`/api/telegram/channels/${channelId}/toggle`, { method: 'PATCH' });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(data.message || 'Đã cập nhật trạng thái kênh', 'success');
            await loadTelegramChannels();
        } else {
            showToast('Lỗi cập nhật: ' + (data.detail || data.message || 'Thất bại'), true);
            if (checkboxEl) checkboxEl.checked = !checkboxEl.checked;
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, true);
        if (checkboxEl) checkboxEl.checked = !checkboxEl.checked;
    }
}

function openAddTelegramChannelModal() {
    const idEl = document.getElementById('teleModalChannelId');
    const nameEl = document.getElementById('teleModalName');
    const chatEl = document.getElementById('teleModalChatId');
    const activeEl = document.getElementById('teleModalActive');
    const titleEl = document.getElementById('teleModalTitle');

    const n10k = document.getElementById('teleModalNotify10k');
    const nIssues = document.getElementById('teleModalNotifyIssues');
    const nDaily = document.getElementById('teleModalNotifyDailyReport');
    const rTime = document.getElementById('teleModalReportTime');

    if (idEl) idEl.value = '';
    if (nameEl) nameEl.value = '';
    if (chatEl) chatEl.value = '';
    if (activeEl) activeEl.checked = true;
    if (titleEl) titleEl.innerHTML = '<i class="fa-brands fa-telegram text-cyan"></i> Thêm Kênh Telegram Mới';

    if (n10k) n10k.checked = true;
    if (nIssues) nIssues.checked = true;
    if (nDaily) nDaily.checked = true;
    if (rTime) rTime.value = '21:00';
    toggleDailyTimeRow(true);

    const modal = document.getElementById('telegramChannelModal');
    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('active');
        if (nameEl) setTimeout(() => nameEl.focus(), 50);
    }
}

function openEditTelegramChannelModal(channel) {
    if (!channel) return;
    const idEl = document.getElementById('teleModalChannelId');
    const nameEl = document.getElementById('teleModalName');
    const chatEl = document.getElementById('teleModalChatId');
    const activeEl = document.getElementById('teleModalActive');
    const titleEl = document.getElementById('teleModalTitle');

    const n10k = document.getElementById('teleModalNotify10k');
    const nIssues = document.getElementById('teleModalNotifyIssues');
    const nDaily = document.getElementById('teleModalNotifyDailyReport');
    const rTime = document.getElementById('teleModalReportTime');

    if (idEl) idEl.value = channel.id || '';
    if (nameEl) nameEl.value = channel.name || '';
    if (chatEl) chatEl.value = channel.chat_id || '';
    if (activeEl) activeEl.checked = (channel.is_active !== 0 && channel.is_active !== false);
    if (titleEl) titleEl.innerHTML = '<i class="fa-solid fa-pen-to-square text-cyan"></i> Chỉnh Sửa Kênh Telegram';

    if (n10k) n10k.checked = channel.notify_10k !== 0;
    if (nIssues) nIssues.checked = channel.notify_issues !== 0;
    if (nDaily) nDaily.checked = channel.notify_daily_report !== 0;
    if (rTime) rTime.value = channel.daily_report_time || '21:00';
    toggleDailyTimeRow(channel.notify_daily_report !== 0);

    const modal = document.getElementById('telegramChannelModal');
    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('active');
        if (nameEl) setTimeout(() => nameEl.focus(), 50);
    }
}

function closeTelegramChannelModal() {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
        document.activeElement.blur();
    }
    const modal = document.getElementById('telegramChannelModal');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('active');
    }
}

async function saveTelegramChannelModal(btn) {
    const id = document.getElementById('teleModalChannelId')?.value;
    const name = (document.getElementById('teleModalName')?.value || '').trim();
    const chatId = (document.getElementById('teleModalChatId')?.value || '').trim();
    const isActive = !!document.getElementById('teleModalActive')?.checked;

    const notify10k = !!document.getElementById('teleModalNotify10k')?.checked;
    const notifyIssues = !!document.getElementById('teleModalNotifyIssues')?.checked;
    const notifyDaily = !!document.getElementById('teleModalNotifyDailyReport')?.checked;
    const reportTime = (document.getElementById('teleModalReportTime')?.value || '21:00').trim();

    if (!name) {
        markInputError('teleModalName', 'Vui lòng nhập tên gợi nhớ cho kênh Telegram!');
        return;
    }
    if (!chatId) {
        markInputError('teleModalChatId', 'Vui lòng nhập Chat ID hoặc Channel ID Telegram (Ví dụ: -100xxxxxxxxxx)!');
        return;
    }
    if (notifyDaily && reportTime && !isValidTimeHHMM(reportTime)) {
        markInputError('teleModalReportTime', `Khung giờ báo cáo "${reportTime}" không hợp lệ! Định dạng chuẩn: HH:MM (00:00 - 23:59)`);
        return;
    }

    const originalHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang lưu...';
    }

    const payload = {
        name: name,
        chat_id: chatId,
        is_active: isActive,
        notify_10k: notify10k,
        notify_issues: notifyIssues,
        notify_daily_report: notifyDaily,
        daily_report_time: reportTime
    };

    try {
        let res;
        if (id) {
            res = await fetch(`/api/telegram/channels/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } else {
            res = await fetch('/api/telegram/channels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        }
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`✅ ${data.message || 'Lưu kênh Telegram thành công!'}`, 'success');
            closeTelegramChannelModal();
            await loadTelegramChannels();
        } else {
            showToast('Lỗi lưu kênh: ' + (data.detail || data.message || 'Thất bại'), 'error');
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }
}

async function deleteTelegramChannel(channelId, channelName) {
    const ok = await showConfirmDialog({
        title: 'Xóa Kênh Telegram',
        message: `Bạn có chắc chắn muốn xóa kênh Telegram "${channelName}" khỏi danh sách nhận thông báo?`,
        confirmText: 'Xóa Kênh',
        confirmClass: 'btn-danger'
    });
    if (!ok) return;

    try {
        const res = await fetch(`/api/telegram/channels/${channelId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`✅ ${data.message || 'Đã xóa kênh Telegram!'}`, 'success');
            await loadTelegramChannels();
        } else {
            showToast('Lỗi khi xóa: ' + (data.detail || data.message || 'Thất bại'), true);
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, true);
    }
}

async function testTelegramChannelMode(channelId, mode, e) {
    if (e) {
        if (typeof e.preventDefault === 'function') e.preventDefault();
        if (typeof e.stopPropagation === 'function') e.stopPropagation();
    }
    // Đóng dropdown menu
    const menu = document.getElementById(`teleTestMenu_${channelId}`);
    if (menu) menu.classList.remove('show');

    const parentBtn = document.getElementById(`btnTestTele_${channelId}`);
    const originalHtml = parentBtn ? parentBtn.innerHTML : '';
    if (parentBtn) {
        parentBtn.disabled = true;
        parentBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    }

    const modeLabels = {
        'connection': 'kết nối',
        '10k': 'cảnh báo 10K',
        'issue': 'báo lỗi & cách sửa',
        'daily_report': 'báo cáo ngày'
    };
    showToast(`Đang gửi tin nhắn thử nghiệm (${modeLabels[mode] || mode}) tới kênh...`);

    try {
        const res = await fetch(`/api/telegram/channels/${channelId}/test?mode=${mode}`, { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`✅ ${data.message}`, 'success');
        } else {
            showToast('❌ ' + (data.detail || data.message || 'Lỗi gửi tin nhắn test'), true);
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, true);
    } finally {
        if (parentBtn) {
            parentBtn.disabled = false;
            parentBtn.innerHTML = originalHtml;
        }
    }
}

async function testTelegramChannel(channelId, btn) {
    return testTelegramChannelMode(channelId, 'connection', btn);
}

function togglePasswordVisibility(inputId, triggerEl) {
    const input = document.getElementById(inputId);
    if (!input) return;
    if (input.type === 'password') {
        input.type = 'text';
        if (triggerEl) triggerEl.innerHTML = '<i class="fa-solid fa-eye-slash"></i> Ẩn Token';
    } else {
        input.type = 'password';
        if (triggerEl) triggerEl.innerHTML = '<i class="fa-solid fa-eye"></i> Hiện Token';
    }
}

// Backdrop click close for modals
document.addEventListener('DOMContentLoaded', () => {
    const teleModal = document.getElementById('telegramChannelModal');
    if (teleModal) {
        teleModal.addEventListener('click', (e) => {
            if (e.target === teleModal) {
                closeTelegramChannelModal();
            }
        });
    }

    const issuesModal = document.getElementById('modalSystemIssues');
    if (issuesModal) {
        issuesModal.addEventListener('click', (e) => {
            if (e.target === issuesModal) {
                closeSystemIssuesModal();
            }
        });
    }

    const diagModal = document.getElementById('modalDiagnostics');
    if (diagModal) {
        diagModal.addEventListener('click', (e) => {
            if (e.target === diagModal) {
                closeDiagnosticsModal();
            }
        });
    }
});

// =========================================================================
// SYSTEM LOGS, FILE DEBUGGING, DIAGNOSTICS & ISSUE RESOLUTION
// =========================================================================

let currentLogsSubTab = 'file';
let fileLogSearchDebounce = null;

function switchLogsSubTab(subtab) {
    currentLogsSubTab = subtab;
    const btnFile = document.getElementById('btnTabFileLogs');
    const btnLive = document.getElementById('btnTabLiveLogs');
    const btnDiag = document.getElementById('btnTabDiagnostics');
    const viewFile = document.getElementById('subtabFileLogsView');
    const viewLive = document.getElementById('subtabLiveLogsView');
    const viewDiag = document.getElementById('subtabDiagnosticsView');
    const headerActions = document.getElementById('fileLogHeaderActions');
    const actionButtons = document.getElementById('fileLogActionButtons');

    if (btnFile) btnFile.classList.toggle('active', subtab === 'file');
    if (btnLive) btnLive.classList.toggle('active', subtab === 'live');
    if (btnDiag) btnDiag.classList.toggle('active', subtab === 'diag');

    if (viewFile) viewFile.style.display = subtab === 'file' ? 'block' : 'none';
    if (viewLive) viewLive.style.display = subtab === 'live' ? 'block' : 'none';
    if (viewDiag) viewDiag.style.display = subtab === 'diag' ? 'block' : 'none';
    if (headerActions) headerActions.style.display = subtab === 'file' ? 'inline-flex' : 'none';
    if (actionButtons) actionButtons.style.display = subtab === 'file' ? 'inline-flex' : 'none';

    if (subtab === 'file') {
        loadFileLogs();
    } else if (subtab === 'live') {
        loadDashboardStats();
    } else if (subtab === 'diag') {
        runDiagnosticsCheck(false);
    }
}

async function loadFileLogs() {
    const terminal = document.getElementById('fileLogTerminal');
    const metaInfo = document.getElementById('fileLogMetaInfo');
    const level = document.getElementById('fileLogLevelFilter')?.value || 'ALL';
    const limit = document.getElementById('fileLogLimitSelect')?.value || '500';
    const search = (document.getElementById('fileLogSearchInput')?.value || '').trim();

    if (!terminal) return;

    try {
        const url = `/api/system/logs/file?limit=${limit}&level=${level}&search=${encodeURIComponent(search)}`;
        const res = await fetch(url);
        const data = await res.json();

        if (metaInfo && data.file_info) {
            metaInfo.textContent = `app.log (${data.file_info.size_formatted}) • Cập nhật: ${data.file_info.modified_time || 'N/A'}`;
        }

        if (!data.logs || data.logs.length === 0) {
            terminal.innerHTML = `<div class="enhanced-log-entry" style="color:var(--text-muted); justify-content:center; padding: 30px;">
                <i class="fa-solid fa-file-circle-question"></i> Không có dòng log nào phù hợp với bộ lọc (Mức: ${level}, Tìm: "${escapeHtml(search)}")
            </div>`;
            return;
        }

        terminal.innerHTML = data.logs.map(entry => {
            const lvl = (entry.level || 'INFO').toUpperCase();
            const cls = lvl === 'ERROR' || lvl === 'CRITICAL' ? 'lvl-error' : (lvl === 'WARNING' ? 'lvl-warning' : (lvl === 'DEBUG' ? 'lvl-debug' : 'lvl-info'));
            return `
            <div class="enhanced-log-entry ${cls}">
                <span class="log-time">${escapeHtml(entry.time || '')}</span>
                <span class="log-lvl-badge">${escapeHtml(lvl)}</span>
                ${entry.source ? `<span class="log-source">[${escapeHtml(entry.source)}]</span>` : ''}
                <div class="log-msg">${escapeHtml(entry.message || entry.raw || '')}</div>
            </div>
            `;
        }).join('');

        // Auto-scroll to bottom if checked
        const chkScroll = document.getElementById('chkAutoScrollFileLog');
        if (chkScroll && chkScroll.checked) {
            terminal.scrollTop = terminal.scrollHeight;
        }
    } catch (err) {
        terminal.innerHTML = `<div class="enhanced-log-entry lvl-error">
            <span class="log-lvl-badge">ERROR</span>
            <div class="log-msg">Không thể đọc file log từ máy chủ: ${escapeHtml(err.message)}</div>
        </div>`;
    }
}

function handleFileLogSearch(e) {
    if (e.key === 'Enter') {
        loadFileLogs();
        return;
    }
    clearTimeout(fileLogSearchDebounce);
    fileLogSearchDebounce = setTimeout(() => {
        loadFileLogs();
    }, 400);
}

async function confirmClearFileLog() {
    const ok = await showConfirmDialog({
        title: 'Làm Sạch File Log',
        message: 'Bạn có chắc chắn muốn làm sạch toàn bộ nội dung file log trên đĩa (app.log)?',
        details: 'Thao tác này hữu ích khi muốn xóa log cũ trước khi chạy test thử nghiệm mới.',
        confirmText: 'Làm Sạch Log',
        confirmClass: 'btn-danger'
    });
    if (!ok) return;
    try {
        const res = await fetch('/api/system/logs/clear', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('✅ Đã làm sạch file log thành công!');
            loadFileLogs();
        } else {
            showToast('Lỗi khi làm sạch file log', true);
        }
    } catch (err) {
        showToast('Lỗi: ' + err.message, true);
    }
}

// =========================================================================
// SYSTEM ACTIVE ISSUES MODAL & RESOLUTION
// =========================================================================

function openSystemIssuesModal() {
    const modal = document.getElementById('modalSystemIssues');
    if (modal) {
        modal.classList.add('show');
        modal.classList.add('active');
        loadSystemIssues();
    }
}

function closeSystemIssuesModal() {
    const modal = document.getElementById('modalSystemIssues');
    if (modal) {
        modal.classList.remove('show');
        modal.classList.remove('active');
    }
}

async function loadSystemIssues() {
    const body = document.getElementById('systemIssuesModalBody');
    const badge = document.getElementById('issuesSummaryBadge');
    if (!body) return;

    body.innerHTML = `<div style="text-align: center; padding: 40px 20px;">
        <div style="font-size: 32px; color: var(--accent-cyan); margin-bottom: 12px;"><i class="fa-solid fa-circle-notch fa-spin"></i></div>
        <h4 style="margin: 0; font-size: 15px; font-weight: 600;">Đang quét toàn diện các cảnh báo & sự cố...</h4>
        <p class="mt-2" style="color: var(--text-muted); font-size: 13px;">Kiểm tra tài khoản TikTok, proxy, lỗi video YouTube, render và hạn ngạch AI.</p>
    </div>`;

    try {
        const res = await fetch('/api/system/active-issues');
        const data = await res.json();

        if (badge) {
            badge.textContent = `Tổng cộng: ${data.total_count} vấn đề (${data.has_critical ? 'Có lỗi nghiêm trọng' : 'Chỉ cảnh báo'})`;
        }

        if (!data.issues || data.issues.length === 0) {
            body.innerHTML = `
                <div style="text-align: center; padding: 40px 20px;">
                    <div style="width: 64px; height: 64px; border-radius: 50%; background: rgba(16, 185, 129, 0.15); color: #10b981; display: inline-flex; align-items: center; justify-content: center; font-size: 28px; margin-bottom: 16px;">
                        <i class="fa-solid fa-circle-check"></i>
                    </div>
                    <h4 style="color: var(--text-primary); font-size: 17px; margin-bottom: 6px;">Hệ Thống Hoạt Động Hoàn Hảo!</h4>
                    <p style="color: var(--text-muted); font-size: 13.5px; max-width: 480px; margin: 0 auto;">
                        Không phát hiện lỗi tải video, proxy chết, tài khoản bị khóa hay hết hạn mức AI nào. Toàn bộ tiến trình Auto-Pilot đang sẵn sàng.
                    </p>
                </div>
            `;
            return;
        }

        body.innerHTML = data.issues.map(issue => {
            const isErr = issue.severity === 'error';
            let icon = 'fa-triangle-exclamation text-warning';
            let actionBtn = '';

            if (issue.category === 'tiktok_account') {
                icon = isErr ? 'fa-ban text-danger' : 'fa-user-shield text-warning';
                actionBtn = `<button class="btn btn-xs btn-secondary" onclick="closeSystemIssuesModal(); switchTab('tab-gpm-farm');"><i class="fa-solid fa-users-gear"></i> Mở Nick GPM</button>`;
            } else if (issue.category === 'video_error') {
                icon = 'fa-video-slash text-danger';
                actionBtn = `<button class="btn btn-xs btn-secondary" onclick="closeSystemIssuesModal(); switchTab('tab-sources');"><i class="fa-brands fa-youtube"></i> Xem Nguồn</button>`;
            } else if (issue.category === 'upload_failure') {
                icon = 'fa-upload text-danger';
                actionBtn = `<button class="btn btn-xs btn-secondary" onclick="closeSystemIssuesModal(); switchTab('tab-pipeline-queue');"><i class="fa-solid fa-list-check"></i> Hàng Đợi</button>`;
            } else if (issue.category === 'ai_limit') {
                icon = 'fa-brain text-warning';
                actionBtn = `<button class="btn btn-xs btn-secondary" onclick="closeSystemIssuesModal(); switchTab('tab-settings');"><i class="fa-solid fa-gear"></i> Cài Đặt AI</button>`;
            } else if (issue.category === 'system_service') {
                icon = 'fa-power-off text-warning';
                actionBtn = `<button class="btn btn-xs btn-secondary" onclick="syncGPMProfiles(this)"><i class="fa-solid fa-rotate"></i> Kết Nối Lại</button>`;
            }

            return `
            <div class="issue-card ${isErr ? 'error' : 'warning'}">
                <div style="font-size: 22px; flex-shrink: 0;">
                    <i class="fa-solid ${icon}"></i>
                </div>
                <div class="issue-card-content">
                    <div class="issue-card-header">
                        <span class="issue-card-title">${escapeHtml(issue.title)}</span>
                        ${issue.target ? `<span class="issue-card-target">${escapeHtml(issue.target)}</span>` : ''}
                        <span class="issue-card-time"><i class="fa-regular fa-clock"></i> ${escapeHtml(issue.time || '')}</span>
                    </div>
                    <div class="issue-card-msg">${escapeHtml(issue.message)}</div>
                </div>
                ${actionBtn ? `<div class="issue-card-action">${actionBtn}</div>` : ''}
            </div>
            `;
        }).join('');

    } catch (err) {
        body.innerHTML = `<div class="diag-action-item error">
            <div class="diag-action-icon"><i class="fa-solid fa-triangle-exclamation"></i></div>
            <div class="diag-action-content">
                <h5>Lỗi truy vấn cảnh báo hệ thống</h5>
                <p>${escapeHtml(err.message)}</p>
            </div>
        </div>`;
    }
}

// =========================================================================
// SYSTEM DIAGNOSTICS MODAL & EMBEDDED TAB
// =========================================================================

function openDiagnosticsModal() {
    const modal = document.getElementById('modalDiagnostics');
    if (modal) {
        modal.classList.add('show');
        modal.classList.add('active');
        runDiagnosticsCheck(true);
    }
}

function closeDiagnosticsModal() {
    const modal = document.getElementById('modalDiagnostics');
    if (modal) {
        modal.classList.remove('show');
        modal.classList.remove('active');
    }
}

async function runDiagnosticsCheck(inModal = true) {
    const targetEl = inModal
        ? document.getElementById('diagnosticsModalBody')
        : document.getElementById('diagnosticsContentArea');
    const timeBadge = inModal ? document.getElementById('diagLastCheckedTime') : null;
    const topbarBtn = document.getElementById('btnDiagnostics');

    if (topbarBtn) {
        topbarBtn.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Đang Chẩn Đoán...`;
    }

    if (!targetEl) return;

    targetEl.innerHTML = `
        <div style="text-align: center; padding: 45px 20px;">
            <div style="font-size: 38px; color: var(--accent-cyan); margin-bottom: 14px;">
                <i class="fa-solid fa-circle-notch fa-spin"></i>
            </div>
            <h4 style="margin: 0; font-size: 16px; font-weight: 700; color: #fff;">Đang Quét Toàn Diện Môi Trường Cài Đặt...</h4>
            <p style="margin: 8px auto 0 auto; max-width: 500px; color: var(--text-muted); font-size: 13px; line-height: 1.5;">
                Kiểm tra FFmpeg video engine, NVIDIA GPU NVENC, Node.js yt-dlp, Playwright automation, GPMLogin API, AI Keys và quyền ghi thư mục lưu trữ.
            </p>
            <div style="display: inline-flex; align-items: center; gap: 8px; margin-top: 18px; padding: 6px 16px; border-radius: 20px; background: rgba(0,242,254,0.1); border: 1px solid rgba(0,242,254,0.3); font-size: 12px; color: var(--accent-cyan);">
                <i class="fa-solid fa-bolt fa-fade"></i> Vui lòng đợi trong giây lát...
            </div>
        </div>
    `;

    try {
        const res = await fetch('/api/system/diagnostics');
        if (!res.ok) {
            throw new Error(`Máy chủ phản hồi mã lỗi ${res.status}. Vui lòng thử lại sau giây lát.`);
        }
        const data = await res.json();
        if (!data || !data.checks) {
            throw new Error(data && data.detail ? data.detail : 'Dữ liệu chẩn đoán từ máy chủ không hợp lệ.');
        }

        if (timeBadge) {
            timeBadge.textContent = `Hệ điều hành: ${data.checks.python?.os || 'Windows'}`;
        }

        const overall = data.overall_status;
        const bannerColor = overall === 'ok' ? 'rgba(16, 185, 129, 0.15)' : (overall === 'warning' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(239, 68, 68, 0.15)');
        const bannerBorder = overall === 'ok' ? '#10b981' : (overall === 'warning' ? '#f59e0b' : '#ef4444');
        const bannerIcon = overall === 'ok' ? 'fa-circle-check text-success' : (overall === 'warning' ? 'fa-triangle-exclamation text-warning' : 'fa-circle-xmark text-danger');
        const bannerTitle = overall === 'ok' ? 'MÔI TRƯỜNG HOẠT ĐỘNG HOÀN TOÀN TỐT' : (overall === 'warning' ? 'MÔI TRƯỜNG HOẠT ĐỘNG TẠM THỜI (CÓ LƯU Ý)' : 'CẦN KHẮC PHỤC CÀI ĐẶT TRÊN MÁY TÍNH');

        let html = `
            <div style="background: ${bannerColor}; border: 1px solid ${bannerBorder}; border-radius: 8px; padding: 14px 18px; margin-bottom: 18px; display: flex; align-items: center; gap: 14px;">
                <div style="font-size: 26px;"><i class="fa-solid ${bannerIcon}"></i></div>
                <div>
                    <h4 style="margin: 0; font-size: 15px; font-weight: 700;">${bannerTitle}</h4>
                    <p style="margin: 2px 0 0 0; font-size: 12.5px; opacity: 0.9;">
                        ${overall === 'ok' ? 'Tất cả các thành phần FFmpeg, GPU, Node.js, Playwright và API Keys đều hoạt động bình thường.' : 'Vui lòng xem các khuyến nghị và hướng dẫn bên dưới để đảm bảo ứng dụng không gặp lỗi.'}
                    </p>
                </div>
            </div>
        `;

        // Render Action Items callouts if any
        if (data.action_items && data.action_items.length > 0) {
            html += `<h5 style="font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px;">Lưu Ý Cần Khắc Phục (${data.action_items.length})</h5>`;
            html += data.action_items.map(item => `
                <div class="diag-action-item ${item.type}">
                    <div class="diag-action-icon"><i class="fa-solid fa-circle-exclamation"></i></div>
                    <div class="diag-action-content">
                        <h5>${escapeHtml(item.title)} <span style="font-size: 11px; font-weight: normal; opacity: 0.8;">(${escapeHtml(item.category)})</span></h5>
                        <p>${escapeHtml(item.message)}</p>
                    </div>
                </div>
            `).join('');
        }

        // Render Component Cards Grid
        html += `<h5 style="font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin: 18px 0 10px 0;">Chi Tiết Từng Phân Hệ</h5>`;
        html += `<div class="diag-grid">`;

        // Card 1: FFmpeg & NVENC
        const ff = data.checks.ffmpeg;
        const isFfOk = ff && (ff.status === 'ok' || ff.status === 'info');
        html += `
            <div class="diag-card">
                <div class="diag-card-header">
                    <span class="diag-card-title"><i class="fa-solid fa-film text-accent"></i> FFmpeg & Render</span>
                    <span class="badge ${isFfOk ? 'badge-success' : 'badge-danger'}">${isFfOk ? (ff.nvenc_accelerated ? 'GPU NVENC' : 'Sẵn Sàng') : 'Thiếu'}</span>
                </div>
                <div class="diag-card-body">
                    <div class="diag-meta-row"><span class="diag-meta-label">Bộ mã hóa:</span> <span class="diag-meta-value">${escapeHtml(ff.encoder || 'libx264')}</span></div>
                    <div class="diag-meta-row"><span class="diag-meta-label">GPU NVENC:</span> <span class="diag-meta-value">${ff.nvenc_accelerated ? '✅ Hỗ trợ' : '⚪ Không (Dùng CPU)'}</span></div>
                    <div class="diag-meta-row" style="font-size: 11px;"><span class="diag-meta-label">Phiên bản:</span> <span class="diag-meta-value" style="font-size: 11px;">${escapeHtml((ff.version || '').slice(0, 35))}</span></div>
                </div>
            </div>
        `;

        // Card 2: Node.js (yt-dlp)
        const node = data.checks.nodejs;
        html += `
            <div class="diag-card">
                <div class="diag-card-header">
                    <span class="diag-card-title"><i class="fa-brands fa-node-js" style="color:#22c55e;"></i> Node.js Runtime</span>
                    <span class="badge ${node.installed ? 'badge-success' : 'badge-warning'}">${node.installed ? 'Sẵn Sàng' : 'Chưa Cài'}</span>
                </div>
                <div class="diag-card-body">
                    <div class="diag-meta-row"><span class="diag-meta-label">Tác vụ:</span> <span class="diag-meta-value">Giải mã chữ ký YouTube</span></div>
                    <div class="diag-meta-row"><span class="diag-meta-label">Phiên bản:</span> <span class="diag-meta-value">${escapeHtml(node.version || 'Chưa cài')}</span></div>
                    <div class="diag-meta-row" style="font-size: 11px;"><span class="diag-meta-label">Đường dẫn:</span> <span class="diag-meta-value" style="font-size: 10px;">${escapeHtml((node.path || '').slice(-30))}</span></div>
                </div>
            </div>
        `;

        // Card 3: Playwright Automation
        const pw = data.checks.playwright;
        html += `
            <div class="diag-card">
                <div class="diag-card-header">
                    <span class="diag-card-title"><i class="fa-solid fa-robot" style="color:#ec4899;"></i> Playwright Browser</span>
                    <span class="badge ${pw.installed ? 'badge-success' : 'badge-danger'}">${pw.installed ? 'Đã Cài' : 'Thiếu'}</span>
                </div>
                <div class="diag-card-body">
                    <div class="diag-meta-row"><span class="diag-meta-label">Tác vụ:</span> <span class="diag-meta-value">Tự đăng TikTok qua GPM</span></div>
                    <div class="diag-meta-row"><span class="diag-meta-label">Trạng thái:</span> <span class="diag-meta-value">${escapeHtml(pw.detail || 'OK')}</span></div>
                </div>
            </div>
        `;

        // Card 4: GPMLogin App API
        const gpm = data.checks.gpm;
        html += `
            <div class="diag-card">
                <div class="diag-card-header">
                    <span class="diag-card-title"><i class="fa-solid fa-globe" style="color:#06b6d4;"></i> GPMLogin Local</span>
                    <span class="badge ${gpm.running ? 'badge-success' : 'badge-danger'}">${gpm.running ? 'Online' : 'Offline'}</span>
                </div>
                <div class="diag-card-body">
                    <div class="diag-meta-row"><span class="diag-meta-label">Cổng kết nối:</span> <span class="diag-meta-value">${escapeHtml(gpm.api_url || 'N/A')}</span></div>
                    <div class="diag-meta-row"><span class="diag-meta-label">Số Profile:</span> <span class="diag-meta-value">${gpm.profile_count || 0} Profiles</span></div>
                </div>
            </div>
        `;

        // Card 5: AI Cloud Providers
        const ai = data.checks.ai;
        html += `
            <div class="diag-card">
                <div class="diag-card-header">
                    <span class="diag-card-title"><i class="fa-solid fa-brain" style="color:#a855f7;"></i> AI Cloud & Models</span>
                    <span class="badge ${ai.status === 'ok' ? 'badge-success' : 'badge-warning'}">${ai.status === 'ok' ? 'Đã Nhập Key' : 'Chưa Có Key'}</span>
                </div>
                <div class="diag-card-body">
                    <div class="diag-meta-row"><span class="diag-meta-label">Provider chính:</span> <span class="diag-meta-value">${escapeHtml((ai.active_provider || '').toUpperCase())}</span></div>
                    <div class="diag-meta-row"><span class="diag-meta-label">DeepSeek / Gemini:</span> <span class="diag-meta-value">${ai.has_deepseek ? '✅ DeepSeek' : '⚪'} ${ai.has_gemini ? '✅ Gemini' : '⚪'}</span></div>
                    <div class="diag-meta-row"><span class="diag-meta-label">faster-whisper:</span> <span class="diag-meta-value">${ai.whisper_installed ? '✅ Sẵn sàng (' + ai.whisper_model_size + ')' : '⚪ Chưa cài'}</span></div>
                </div>
            </div>
        `;

        // Card 6: YouTube Data API v3
        const yt = data.checks.youtube;
        html += `
            <div class="diag-card">
                <div class="diag-card-header">
                    <span class="diag-card-title"><i class="fa-brands fa-youtube" style="color:#ef4444;"></i> YouTube API Keys</span>
                    <span class="badge ${yt.configured ? 'badge-success' : 'badge-warning'}">${yt.configured ? `${yt.key_count} Key(s)` : 'Chưa Có'}</span>
                </div>
                <div class="diag-card-body">
                    <div class="diag-meta-row"><span class="diag-meta-label">Tác vụ:</span> <span class="diag-meta-value">Quét ngách & theo dõi kênh</span></div>
                    <div class="diag-meta-row"><span class="diag-meta-label">Dung lượng:</span> <span class="diag-meta-value">${yt.key_count * 10000} units/ngày</span></div>
                </div>
            </div>
        `;

        // Card 7: Storage & Permissions
        const st = data.checks.storage;
        const py = data.checks.python;
        html += `
            <div class="diag-card">
                <div class="diag-card-header">
                    <span class="diag-card-title"><i class="fa-solid fa-hard-drive" style="color:#eab308;"></i> Dung Lượng & Ổ Đĩa</span>
                    <span class="badge ${st.status === 'ok' ? 'badge-success' : 'badge-danger'}">${st.status === 'ok' ? 'Quyền Ghi OK' : 'Lỗi Quyền Ghi'}</span>
                </div>
                <div class="diag-card-body">
                    <div class="diag-meta-row"><span class="diag-meta-label">Dung lượng trống:</span> <span class="diag-meta-value">${py.disk_free_gb} GB (${py.disk_percent_free}% còn lại)</span></div>
                    <div class="diag-meta-row"><span class="diag-meta-label">Thư mục log:</span> <span class="diag-meta-value">data/logs (OK)</span></div>
                </div>
            </div>
        `;

        html += `</div>`;

        targetEl.innerHTML = html;

    } catch (err) {
        targetEl.innerHTML = `<div class="diag-action-item error">
            <div class="diag-action-icon"><i class="fa-solid fa-triangle-exclamation"></i></div>
            <div class="diag-action-content">
                <h5>Không thể chạy chẩn đoán hệ thống</h5>
                <p>${escapeHtml(err.message)}</p>
            </div>
        </div>`;
    } finally {
        if (topbarBtn) {
            topbarBtn.innerHTML = `<i class="fa-solid fa-stethoscope"></i> Chẩn Đoán`;
        }
    }
}

// ==========================================================================
// --- AUDIO STUDIO (KHO ÂM THANH & BGM PLAYLIST) ---
// ==========================================================================

let cachedAudioCategories = [];
let currentSelectedAudioCategory = 'general';
let rawAudioSearchResults = [];
let audioSortField = 'default';
let audioSortAsc = false;
let audioFilterDuration = 'all';
let audioFilterDownload = 'all';
let audioFilterKeyword = '';

let currentPreviewAudio = null;
let currentPlayingBtnId = null;
let currentPreviewMode = null; // 'html5' | 'iframe'

// Chuyển đổi Sub-tab trong Kho Âm Thanh
function switchAudioSubTab(sub) {
    const btnSearch = document.getElementById('btnAudioSubnavSearch');
    const btnLibrary = document.getElementById('btnAudioSubnavLibrary');
    const viewSearch = document.getElementById('audioSubViewSearch');
    const viewLibrary = document.getElementById('audioSubViewLibrary');

    if (sub === 'search') {
        btnSearch?.classList.add('active');
        btnLibrary?.classList.remove('active');
        if (viewSearch) viewSearch.style.display = 'block';
        if (viewLibrary) viewLibrary.style.display = 'none';
    } else {
        btnLibrary?.classList.add('active');
        btnSearch?.classList.remove('active');
        if (viewSearch) viewSearch.style.display = 'none';
        if (viewLibrary) viewLibrary.style.display = 'block';
        loadAudioCategories();
    }
}

// 1. Tải danh sách thư mục nhạc nền (Categories)
async function loadAudioCategories() {
    try {
        const res = await fetch('/api/audio/categories');
        const data = await res.json();
        if (data.status === 'success') {
            cachedAudioCategories = data.categories || [];
            renderAudioCategoryChips(cachedAudioCategories);
            populateAllBgmSelects(cachedAudioCategories);

            // Cập nhật tổng số bài hát trên badge
            const totalTracks = cachedAudioCategories.reduce((sum, c) => sum + (c.track_count || 0), 0);
            const badge = document.getElementById('audioLibraryTotalCountBadge');
            if (badge) badge.textContent = totalTracks;

            // Load bài hát cho category hiện tại
            if (!cachedAudioCategories.some(c => c.id === currentSelectedAudioCategory)) {
                currentSelectedAudioCategory = cachedAudioCategories[0]?.id || 'general';
            }
            loadAudioTracks(currentSelectedAudioCategory);
        }
    } catch (err) {
        console.error('Lỗi tải danh mục âm thanh:', err);
    }
}

// Render các chip thư mục nhạc (hỗ trợ 200+ thư mục với popover)
let popoverFolderSearchTerm = '';

function renderAudioCategoryChips(categories) {
    const container = document.getElementById('audioCategoryChipsContainer');
    if (!container) return;

    if (!categories.length) {
        container.innerHTML = '<span class="text-muted">Chưa có thư mục nhạc nào.</span>';
        return;
    }

    const maxVisible = 10;
    const visibleChips = categories.slice(0, maxVisible);
    const overflowChips = categories.slice(maxVisible);
    const isOverflowSelected = overflowChips.some(c => c.id === currentSelectedAudioCategory);

    let html = visibleChips.map(cat => {
        const isSelected = cat.id === currentSelectedAudioCategory;
        const dispName = escapeHtml(cat.display_name || cat.name);
        return `
            <div class="audio-chip-wrapper ${isSelected ? 'active' : ''}">
                <button type="button" class="audio-chip ${isSelected ? 'active' : ''}"
                    onclick="selectAudioCategory('${escapeHtml(cat.id)}')">
                    <i class="fa-solid fa-folder"></i>
                    <span>${dispName}</span>
                    <span class="audio-chip-count">${cat.track_count} bài • ${cat.total_size_mb} MB</span>
                </button>
                <div class="audio-chip-actions">
                    <button type="button" class="chip-action-btn has-tooltip tooltip-top" title="Đổi tên thư mục" data-tooltip="Đổi tên thư mục"
                        onclick="event.stopPropagation(); openEditCategoryModal('${escapeHtml(cat.id)}', '${dispName}')">
                        <i class="fa-solid fa-pen"></i>
                    </button>
                    <button type="button" class="chip-action-btn danger has-tooltip tooltip-top" title="Xóa thư mục" data-tooltip="Xóa thư mục"
                        onclick="event.stopPropagation(); deleteCategoryPrompt('${escapeHtml(cat.id)}')">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');

    if (overflowChips.length > 0) {
        html += `
            <div class="audio-more-folders-wrap">
                <button type="button" class="audio-chip audio-chip-more ${isOverflowSelected ? 'active' : ''}"
                    id="btnMoreAudioFolders" onclick="toggleAudioFoldersPopover(event)">
                    <i class="fa-solid fa-folder-tree"></i>
                    <span>+${overflowChips.length} Thư Mục Khác</span>
                    <i class="fa-solid fa-chevron-down" style="font-size:10px; margin-left:4px;"></i>
                </button>
                <div class="audio-folders-popover" id="audioFoldersPopover" style="display:none;" onclick="event.stopPropagation()">
                    <div class="audio-popover-header">
                        <div class="audio-popover-search">
                            <i class="fa-solid fa-magnifying-glass"></i>
                            <input type="text" id="popoverFolderSearch" placeholder="Tìm kiếm trong ${categories.length} thư mục..."
                                value="${escapeHtml(popoverFolderSearchTerm)}"
                                oninput="filterAudioFoldersPopover(this.value)">
                        </div>
                    </div>
                    <div class="audio-popover-list" id="audioPopoverList">
                        <!-- Popover items -->
                    </div>
                </div>
            </div>
        `;
    }

    container.innerHTML = html;

    if (overflowChips.length > 0) {
        renderAudioPopoverItems();
    }
}

function renderAudioPopoverItems() {
    const listEl = document.getElementById('audioPopoverList');
    if (!listEl) return;

    let items = cachedAudioCategories;
    if (popoverFolderSearchTerm) {
        const kw = popoverFolderSearchTerm.toLowerCase();
        items = cachedAudioCategories.filter(c => (c.name || '').toLowerCase().includes(kw) || (c.display_name || '').toLowerCase().includes(kw));
    } else {
        items = cachedAudioCategories.slice(10);
    }

    if (!items.length) {
        listEl.innerHTML = '<div style="text-align:center; padding:16px; color:var(--text-muted); font-size:12px;">Không tìm thấy thư mục nào phù hợp.</div>';
        return;
    }

    listEl.innerHTML = items.map(cat => {
        const isSelected = cat.id === currentSelectedAudioCategory;
        const dispName = escapeHtml(cat.display_name || cat.name);
        return `
            <div class="audio-popover-item ${isSelected ? 'active' : ''}" onclick="selectAudioCategory('${escapeHtml(cat.id)}'); closeAudioFoldersPopover();">
                <div class="audio-popover-item-info">
                    <i class="fa-solid fa-folder text-cyan"></i>
                    <div class="audio-popover-item-texts">
                        <span class="audio-popover-item-name" title="${dispName}">${dispName}</span>
                        <span class="audio-popover-item-meta">${cat.track_count} bài • ${cat.total_size_mb} MB</span>
                    </div>
                </div>
                <div class="audio-popover-item-actions">
                    <button type="button" class="btn-icon-xs has-tooltip tooltip-side-left" 
                        title="Đổi tên thư mục" data-tooltip="Đổi tên thư mục"
                        onclick="event.stopPropagation(); openEditCategoryModal('${escapeHtml(cat.id)}', '${dispName}')">
                        <i class="fa-solid fa-pen"></i>
                    </button>
                    <button type="button" class="btn-icon-xs text-danger has-tooltip tooltip-side-left" 
                        title="Xóa thư mục" data-tooltip="Xóa thư mục"
                        onclick="event.stopPropagation(); deleteCategoryPrompt('${escapeHtml(cat.id)}')">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function filterAudioFoldersPopover(keyword) {
    popoverFolderSearchTerm = keyword.trim();
    renderAudioPopoverItems();
}

function toggleAudioFoldersPopover(event) {
    if (event) event.stopPropagation();
    const pop = document.getElementById('audioFoldersPopover');
    if (!pop) return;
    const isShowing = pop.style.display !== 'none';
    if (isShowing) {
        closeAudioFoldersPopover();
    } else {
        pop.style.display = 'block';
        const inp = document.getElementById('popoverFolderSearch');
        if (inp) inp.focus();
        setTimeout(() => {
            document.addEventListener('click', onDocClickCloseAudioPopover);
        }, 10);
    }
}

function closeAudioFoldersPopover() {
    const pop = document.getElementById('audioFoldersPopover');
    if (pop) pop.style.display = 'none';
    document.removeEventListener('click', onDocClickCloseAudioPopover);
}

function onDocClickCloseAudioPopover(e) {
    const pop = document.getElementById('audioFoldersPopover');
    const btn = document.getElementById('btnMoreAudioFolders');
    if (pop && !pop.contains(e.target) && (!btn || !btn.contains(e.target))) {
        closeAudioFoldersPopover();
    }
}

// Modal đổi tên thư mục nhạc
function openEditCategoryModal(catId, currentDisplayName) {
    const cat = cachedAudioCategories.find(c => c.id === catId);
    const oldIdInput = document.getElementById('editCategoryOldId');
    const dispInput = document.getElementById('editCategoryDisplayName');
    const folderInput = document.getElementById('editCategoryFolderName');
    const modal = document.getElementById('modalEditAudioCategory');

    if (!modal) return;
    if (oldIdInput) oldIdInput.value = catId;
    if (dispInput) dispInput.value = currentDisplayName || (cat ? (cat.display_name || cat.name) : catId);
    if (folderInput) folderInput.value = cat ? cat.name : catId;

    modal.classList.add('active');
}

function closeEditCategoryModal() {
    const modal = document.getElementById('modalEditAudioCategory');
    if (modal) modal.classList.remove('active');
}

async function saveCategoryRename() {
    const oldId = document.getElementById('editCategoryOldId')?.value.trim();
    const displayName = document.getElementById('editCategoryDisplayName')?.value.trim();
    const folderInput = document.getElementById('editCategoryFolderName');
    const folderName = folderInput ? folderInput.value.trim() : '';
    const btn = document.getElementById('btnSaveCategoryRename');

    if (!oldId) {
        showToast('Không xác định được thư mục cần đổi tên!', 'error');
        return;
    }
    if (!folderName) {
        markInputError('editCategoryFolderName', 'Vui lòng nhập tên thư mục mới!');
        return;
    }
    if (!isValidFolderName(folderName)) {
        markInputError('editCategoryFolderName', 'Tên thư mục không được chứa ký tự đặc biệt (/ \\ : * ? " < > |)!');
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang lưu...';
    }

    try {
        const res = await fetch('/api/audio/categories/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_id: oldId, new_name: folderName, display_name: displayName })
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast('✅ Đã đổi tên thư mục nhạc thành công!', 'success');
            closeEditCategoryModal();
            if (currentSelectedAudioCategory === oldId) {
                currentSelectedAudioCategory = data.category.id;
            }
            await loadAudioCategories();
        } else {
            showToast('Lỗi: ' + (data.detail || data.message || 'Không thể đổi tên thư mục'), 'error');
        }
    } catch (err) {
        showToast('Lỗi khi đổi tên thư mục: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-check"></i> Lưu Thay Đổi';
        }
    }
}

async function deleteCategoryPrompt(catId) {
    const cat = cachedAudioCategories.find(c => c.id === catId);
    const rawName = cat ? (cat.display_name || cat.name) : catId;
    const catName = rawName.length > 36 ? rawName.slice(0, 33) + '...' : rawName;
    const trackCount = cat ? cat.track_count : 0;

    const ok = await showConfirmDialog({
        title: 'Xóa Thư Mục Nhạc Nền',
        message: `Bạn có chắc chắn muốn xóa thư mục nhạc "${catName}"?`,
        details: `Lưu ý: Tất cả ${trackCount} bài hát trong thư mục này sẽ bị xóa khỏi máy tính!`,
        confirmText: 'Xóa Thư Mục',
        confirmClass: 'btn-danger'
    });
    if (!ok) return;

    try {
        const res = await fetch(`/api/audio/categories/${encodeURIComponent(catId)}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(`Đã xóa thư mục "${catName}"!`);
            if (currentSelectedAudioCategory === catId) {
                currentSelectedAudioCategory = 'general';
            }
            await loadAudioCategories();
        } else {
            showToast(data.detail || 'Không thể xóa thư mục', true);
        }
    } catch (err) {
        showToast('Lỗi khi xóa thư mục nhạc: ' + err.message, true);
    }
}

// Modal Cài đặt Audio Studio
async function openAudioSettingsModal() {
    const modal = document.getElementById('modalAudioSettings');
    if (!modal) return;
    modal.classList.add('active');

    try {
        const res = await fetch('/api/audio/settings');
        const data = await res.json();
        if (data.status === 'success') {
            const dirInput = document.getElementById('settingAudioMusicDir');
            const maxInput = document.getElementById('settingAudioMaxSize');
            const bitSelect = document.getElementById('settingAudioBitrate');
            const resSelect = document.getElementById('settingAudioMaxResults');
            const normCheck = document.getElementById('settingAudioNormalize');

            if (dirInput) dirInput.value = data.music_dir || '';
            if (maxInput) maxInput.value = data.max_size_mb || 50;
            if (bitSelect) bitSelect.value = data.default_bitrate || '192k';
            if (resSelect) resSelect.value = data.max_search_results || 50;
            if (normCheck) normCheck.checked = Boolean(data.normalize_audio);
        }
    } catch (err) {
        console.error('Lỗi nạp cài đặt audio:', err);
    }
}

function closeAudioSettingsModal() {
    const modal = document.getElementById('modalAudioSettings');
    if (modal) modal.classList.remove('active');
}

async function saveAudioSettings() {
    const dirInput = document.getElementById('settingAudioMusicDir');
    const maxInput = document.getElementById('settingAudioMaxSize');
    const bitSelect = document.getElementById('settingAudioBitrate');
    const resSelect = document.getElementById('settingAudioMaxResults');
    const normCheck = document.getElementById('settingAudioNormalize');
    const btn = document.getElementById('btnSaveAudioSettings');

    const maxSize = maxInput ? parseInt(maxInput.value, 10) : 50;
    const maxResults = resSelect ? parseInt(resSelect.value, 10) : 50;

    if (isNaN(maxSize) || maxSize < 1 || maxSize > 500) {
        markInputError('settingAudioMaxSize', 'Dung lượng tối đa phải từ 1 đến 500 MB!');
        return;
    }
    if (isNaN(maxResults) || maxResults < 1 || maxResults > 100) {
        markInputError('settingAudioMaxResults', 'Số kết quả tìm kiếm tối đa phải từ 1 đến 100!');
        return;
    }

    const payload = {
        music_dir: dirInput ? dirInput.value.trim() : null,
        max_size_mb: maxSize,
        default_bitrate: bitSelect ? bitSelect.value : '192k',
        max_search_results: maxResults,
        normalize_audio: normCheck ? normCheck.checked : true
    };

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang lưu...';
    }

    try {
        const res = await fetch('/api/audio/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast('✅ Đã lưu cài đặt Audio thành công!', 'success');
            closeAudioSettingsModal();
            await loadAudioCategories();
        } else {
            showToast('Lỗi: ' + (data.detail || data.message || 'Không thể lưu cài đặt'), 'error');
        }
    } catch (err) {
        showToast('Lỗi khi lưu cài đặt audio: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-check"></i> Lưu Cài Đặt';
        }
    }
}

// Chọn một danh mục nhạc để xem
function selectAudioCategory(catId) {
    currentSelectedAudioCategory = catId;
    renderAudioCategoryChips(cachedAudioCategories);
    const cat = cachedAudioCategories.find(c => c.id === catId);
    const titleEl = document.getElementById('currentCategoryTitle');
    const uploadTargetEl = document.getElementById('currentUploadTargetCategoryName');
    if (titleEl) titleEl.textContent = cat ? (cat.display_name || cat.name) : catId;
    if (uploadTargetEl) uploadTargetEl.textContent = cat ? cat.name : catId;
    loadAudioTracks(catId);
}

// Tải bài hát trong một danh mục
async function loadAudioTracks(category) {
    const tbody = document.getElementById('localTracksBody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted"><i class="fa-solid fa-spinner fa-spin"></i> Đang nạp danh sách bài hát...</td></tr>';

    try {
        const res = await fetch(`/api/audio/tracks?category=${encodeURIComponent(category)}`);
        const data = await res.json();
        if (data.status === 'success') {
            const tracks = data.tracks || [];
            const countEl = document.getElementById('currentCategoryTrackCount');
            if (countEl) countEl.textContent = `${tracks.length} bài`;
            renderLocalTracksTable(tracks);
        }
    } catch (err) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-danger">Lỗi khi nạp bài hát: ${escapeHtml(err.message)}</td></tr>`;
    }
}

// Render bảng bài hát local
function renderLocalTracksTable(tracks) {
    const tbody = document.getElementById('localTracksBody');
    if (!tbody) return;

    if (!tracks.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-5 text-muted"><i class="fa-solid fa-music fa-2x mb-2" style="opacity:0.3;"></i><br>Chưa có file nhạc nào trong thư mục này. Hãy kéo thả file MP3 hoặc tải từ YouTube!</td></tr>';
        return;
    }

    tbody.innerHTML = tracks.map((t, idx) => {
        const btnId = `btnPlayLocal_${idx}`;
        return `
            <tr>
                <td>
                    <div class="table-text-truncate" style="max-width: 260px; font-weight:600; color:#fff;" title="${escapeHtml(t.filename)}">
                        <i class="fa-solid fa-file-audio text-cyan" style="margin-right:6px;"></i>
                        ${escapeHtml(t.filename)}
                    </div>
                </td>
                <td><span class="badge badge-info">${escapeHtml(t.ext.toUpperCase())}</span></td>
                <td>${t.size_mb} MB</td>
                <td>${escapeHtml(t.modified_at)}</td>
                <td class="text-center">
                    <button type="button" class="audio-preview-btn has-tooltip" id="${btnId}"
                        onclick="togglePlayAudioPreview('${escapeHtml(t.stream_url)}', '${btnId}', '${escapeHtml(t.filename).replace(/'/g, "\\'")}', '', '')"
                        data-tooltip="Bấm để Nghe Thử / Tạm Dừng">
                        <i class="fa-solid fa-play"></i>
                    </button>
                </td>
                <td class="text-center">
                    <button type="button" class="btn btn-sm btn-danger has-tooltip"
                        onclick="deleteAudioTrack('${escapeHtml(t.category)}', '${escapeHtml(t.filename)}')"
                        data-tooltip="Xóa file nhạc này">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

// Làm mới thư viện nhạc
function refreshAudioLibrary() {
    loadAudioCategories();
    showToast('Đã làm mới thư viện nhạc!');
}

// Xóa bài hát local
async function deleteAudioTrack(category, filename) {
    const rawName = filename || '';
    const dispFile = rawName.length > 36 ? rawName.slice(0, 33) + '...' : rawName;
    const ok = await showConfirmDialog({
        title: 'Xóa File Nhạc Khỏi Thư Viện',
        message: `Bạn có chắc muốn xóa file nhạc "${dispFile}"?`,
        details: 'Tệp MP3 sẽ bị xóa vĩnh viễn khỏi máy tính.',
        confirmText: 'Xóa Bài Hát',
        confirmClass: 'btn-danger'
    });
    if (!ok) return;

    try {
        const res = await fetch('/api/audio/tracks', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category, filename })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Đã xóa file nhạc thành công!');
            stopAudioPreview();
            loadAudioCategories();
        } else {
            showToast(data.detail || 'Lỗi khi xóa bài hát', true);
        }
    } catch (err) {
        showToast('Lỗi khi xóa: ' + err.message, true);
    }
}

// --------------------------------------------------------------------------
// --- HỆ THỐNG PHÁT / NGHE THỬ ÂM THANH (PREVIEW DOCK & YOUTUBE PLAYER) ---
// --------------------------------------------------------------------------

// Dừng hoàn toàn nghe thử
function stopAudioPreview() {
    if (currentPreviewAudio) {
        try { currentPreviewAudio.pause(); } catch (_) {}
        currentPreviewAudio = null;
    }

    const container = document.getElementById('audioDockYtContainer');
    if (container) {
        container.innerHTML = '';
    }

    if (currentPlayingBtnId) {
        const prevBtn = document.getElementById(currentPlayingBtnId);
        if (prevBtn) {
            prevBtn.classList.remove('playing');
            prevBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
        }
        currentPlayingBtnId = null;
    }

    currentPreviewMode = null;

    const dock = document.getElementById('audioPreviewDock');
    if (dock) dock.style.display = 'none';
}

// Hiển thị Dock nghe thử
function showAudioPreviewDock({ title, sub, thumb, isLoading }) {
    const dock = document.getElementById('audioPreviewDock');
    if (!dock) return;

    dock.style.display = 'block';

    const titleEl = document.getElementById('audioDockTitle');
    const subEl = document.getElementById('audioDockSub');
    const thumbImg = document.getElementById('audioDockThumb');
    const iconFallback = document.getElementById('audioDockIconFallback');
    const playPauseBtn = document.getElementById('btnDockPlayPause');
    const eq = document.getElementById('audioDockEqualizer');

    if (titleEl) {
        titleEl.textContent = title || 'Đang kết nối âm thanh...';
        titleEl.title = title || '';
    }
    if (subEl) subEl.textContent = sub || 'BGM Preview';

    if (thumb && thumbImg) {
        thumbImg.src = thumb;
        thumbImg.style.display = 'block';
        if (iconFallback) iconFallback.style.display = 'none';
    } else {
        if (thumbImg) thumbImg.style.display = 'none';
        if (iconFallback) iconFallback.style.display = 'flex';
    }

    if (playPauseBtn) {
        playPauseBtn.innerHTML = isLoading ? '<i class="fa-solid fa-spinner fa-spin"></i>' : '<i class="fa-solid fa-pause"></i>';
    }
    if (eq) {
        eq.classList.remove('paused');
    }
}

// Cập nhật trạng thái Dock
function updateAudioPreviewDockState(isPlaying, updatedTitle) {
    const playPauseBtn = document.getElementById('btnDockPlayPause');
    const eq = document.getElementById('audioDockEqualizer');
    const titleEl = document.getElementById('audioDockTitle');

    if (updatedTitle && titleEl) {
        titleEl.textContent = updatedTitle;
        titleEl.title = updatedTitle;
    }

    if (playPauseBtn) {
        playPauseBtn.innerHTML = isPlaying ? '<i class="fa-solid fa-pause"></i>' : '<i class="fa-solid fa-play"></i>';
    }
    if (eq) {
        if (isPlaying) eq.classList.remove('paused');
        else eq.classList.add('paused');
    }
}

// Bật / tắt tạm dừng từ Dock
function toggleDockPlayPause() {
    const playPauseBtn = document.getElementById('btnDockPlayPause');
    const rowBtn = document.getElementById(currentPlayingBtnId);

    if (currentPreviewMode === 'html5' && currentPreviewAudio) {
        if (currentPreviewAudio.paused) {
            currentPreviewAudio.play().then(() => {
                updateAudioPreviewDockState(true);
                if (rowBtn) {
                    rowBtn.classList.add('playing');
                    rowBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
                }
            }).catch(e => showToast('Không thể tiếp tục phát: ' + e.message, true));
        } else {
            currentPreviewAudio.pause();
            updateAudioPreviewDockState(false);
            if (rowBtn) {
                rowBtn.classList.remove('playing');
                rowBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
            }
        }
    } else if (currentPreviewMode === 'iframe') {
        const iframe = document.getElementById('ytAudioPreviewIframe');
        const isPaused = playPauseBtn && playPauseBtn.innerHTML.includes('fa-play');

        if (isPaused) {
            iframe?.contentWindow?.postMessage('{"event":"command","func":"playVideo","args":""}', '*');
            updateAudioPreviewDockState(true);
            if (rowBtn) {
                rowBtn.classList.add('playing');
                rowBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
            }
        } else {
            iframe?.contentWindow?.postMessage('{"event":"command","func":"pauseVideo","args":""}', '*');
            updateAudioPreviewDockState(false);
            if (rowBtn) {
                rowBtn.classList.remove('playing');
                rowBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
            }
        }
    }
}

// Đóng Dock
function closeAudioPreviewDock() {
    stopAudioPreview();
}

// Phát âm thanh YouTube qua iframe (Fallback 100% không bao giờ lỗi CORS/bot)
function playViaYouTubeIframe(videoId, btnId, trackTitle, trackThumb) {
    if (!videoId) {
        showToast('Không tìm thấy Video ID để phát', true);
        stopAudioPreview();
        return;
    }

    const container = document.getElementById('audioDockYtContainer');
    if (!container) return;

    // Chèn iframe YouTube với autoplay và enablejsapi để điều khiển postMessage
    container.innerHTML = `
        <iframe id="ytAudioPreviewIframe"
            src="https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&enablejsapi=1&controls=0"
            allow="autoplay; encrypted-media"
            style="width: 200px; height: 120px; border:0;">
        </iframe>
    `;

    currentPreviewMode = 'iframe';
    const btn = document.getElementById(btnId);
    if (btn) {
        btn.classList.add('playing');
        btn.innerHTML = '<i class="fa-solid fa-pause"></i>';
    }

    updateAudioPreviewDockState(true, trackTitle);
}

// Phát / Dừng nghe thử âm thanh (Tự động nhận diện YouTube URL hoặc Local Stream)
async function togglePlayAudioPreview(streamUrl, btnId, trackTitle, trackThumb, videoId) {
    const btn = document.getElementById(btnId);

    // Nếu đang phát bài này -> Dừng
    if (currentPlayingBtnId === btnId) {
        stopAudioPreview();
        return;
    }

    // Nếu đang phát bài khác -> Dừng bài cũ trước
    stopAudioPreview();

    currentPlayingBtnId = btnId;
    if (btn) {
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    }

    const isYouTube = streamUrl && (streamUrl.includes('youtube.com') || streamUrl.includes('youtu.be') || videoId);
    let cleanVideoId = videoId;
    if (isYouTube && !cleanVideoId) {
        const m = streamUrl.match(/(?:v=|\/|be\/)([a-zA-Z0-9_-]{11})/);
        cleanVideoId = m ? m[1] : '';
    }

    // Mở Dock với trạng thái đang kết nối
    showAudioPreviewDock({
        title: trackTitle || (isYouTube ? 'YouTube Audio' : 'Nhạc Nền Thư Viện'),
        sub: isYouTube ? 'YouTube No-Copyright' : 'Thư viện BGM',
        thumb: trackThumb || '',
        isLoading: true
    });

    if (isYouTube) {
        // Cố gắng lấy Direct Stream URL qua backend để phát nhẹ nhàng qua HTML5
        try {
            const resp = await fetch(`/api/audio/yt-stream-url?url=${encodeURIComponent(streamUrl || cleanVideoId)}`);
            const data = await resp.json();

            if (data && data.stream_url) {
                try {
                    const audio = new Audio(data.stream_url);
                    audio.onended = () => stopAudioPreview();
                    audio.onerror = () => {
                        // Nếu direct stream lỗi CORS hoặc network, fallback ngay sang iframe
                        playViaYouTubeIframe(cleanVideoId || data.video_id, btnId, trackTitle, trackThumb);
                    };

                    await audio.play();
                    currentPreviewAudio = audio;
                    currentPreviewMode = 'html5';

                    if (btn) {
                        btn.classList.add('playing');
                        btn.innerHTML = '<i class="fa-solid fa-pause"></i>';
                    }
                    updateAudioPreviewDockState(true, data.title || trackTitle);
                    return;
                } catch (playErr) {
                    console.warn('HTML5 audio play failed, falling back to YouTube iframe:', playErr);
                }
            }

            // Fallback: Phát qua embedded iframe
            playViaYouTubeIframe(cleanVideoId || (data ? data.video_id : ''), btnId, trackTitle, trackThumb);

        } catch (err) {
            console.warn('Error resolving YouTube stream, falling back to iframe:', err);
            playViaYouTubeIframe(cleanVideoId, btnId, trackTitle, trackThumb);
        }
    } else {
        // Local audio file stream
        try {
            const audio = new Audio(streamUrl);
            audio.onended = () => stopAudioPreview();
            audio.onerror = (e) => {
                showToast('Không thể phát file âm thanh: ' + (e.message || 'Lỗi định dạng'), true);
                stopAudioPreview();
            };

            await audio.play();
            currentPreviewAudio = audio;
            currentPreviewMode = 'html5';

            if (btn) {
                btn.classList.add('playing');
                btn.innerHTML = '<i class="fa-solid fa-pause"></i>';
            }
            updateAudioPreviewDockState(true, trackTitle);
        } catch (err) {
            showToast('Không thể phát âm thanh: ' + err.message, true);
            stopAudioPreview();
        }
    }
}

// Modal Tạo Thư Mục Nhạc Mới
function openCreateAudioCategoryModal() {
    document.getElementById('newCategoryFolderInput').value = '';
    document.getElementById('newCategoryDisplayInput').value = '';
    document.getElementById('modalCreateAudioCategory').classList.add('active');
}

function closeCreateAudioCategoryModal() {
    document.getElementById('modalCreateAudioCategory').classList.remove('active');
}

async function submitCreateAudioCategory() {
    const folderInput = document.getElementById('newCategoryFolderInput');
    const folder = folderInput ? folderInput.value.trim() : '';
    const display = document.getElementById('newCategoryDisplayInput')?.value.trim() || '';
    if (!folder) {
        markInputError('newCategoryFolderInput', 'Vui lòng nhập tên thư mục nhạc!');
        return;
    }
    if (!isValidFolderName(folder)) {
        markInputError('newCategoryFolderInput', 'Tên thư mục không được chứa ký tự đặc biệt (/ \\ : * ? " < > |)!');
        return;
    }

    try {
        const res = await fetch('/api/audio/categories/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: folder, display_name: display || folder })
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`✅ Đã tạo thư mục nhạc "${folder}" thành công!`, 'success');
            closeCreateAudioCategoryModal();
            currentSelectedAudioCategory = data.category.id;
            loadAudioCategories();
        } else {
            showToast('Lỗi: ' + (data.detail || data.message || 'Không thể tạo thư mục'), 'error');
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, 'error');
    }
}

// Xử lý kéo thả Upload file nhạc
async function handleAudioFilesSelected(files) {
    if (!files || !files.length) {
        showToast('Vui lòng chọn ít nhất 1 file âm thanh!', 'warning');
        return;
    }

    const validExtensions = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac'];
    const invalidFiles = Array.from(files).filter(f => !validExtensions.some(ext => f.name.toLowerCase().endsWith(ext)));
    if (invalidFiles.length > 0) {
        showToast(`⚠️ Có ${invalidFiles.length} file không phải định dạng âm thanh hỗ trợ (.mp3, .wav, .aac, .m4a, .flac)!`, 'warning');
        return;
    }

    const targetCategory = currentSelectedAudioCategory || 'general';
    const formData = new FormData();
    formData.append('category', targetCategory);
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    showToast(`Đang tải lên ${files.length} file nhạc vào [${targetCategory}]...`);

    try {
        const res = await fetch('/api/audio/upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`✅ Tải lên thành công ${data.uploaded_count} bài hát!`, 'success');
            loadAudioCategories();
        } else {
            const errs = data.errors ? data.errors.join('; ') : (data.detail || data.message || 'Lỗi tải lên');
            showToast(`Lỗi: ${errs}`, 'error');
        }
    } catch (err) {
        showToast('Lỗi tải lên file nhạc: ' + err.message, 'error');
    } finally {
        const input = document.getElementById('audioFileInput');
        if (input) input.value = '';
    }
}

// Tải nhanh từ YouTube URL trực tiếp trong Thư viện
async function downloadDirectYtAudio() {
    const input = document.getElementById('directYtAudioUrl');
    const btn = document.getElementById('btnDirectDownloadYtAudio');
    const url = input?.value.trim();
    if (!url) {
        markInputError('directYtAudioUrl', 'Vui lòng nhập link YouTube cần tải nhạc MP3!');
        return;
    }
    if (!isValidYouTubeUrl(url)) {
        markInputError('directYtAudioUrl', 'Link YouTube không đúng định dạng!');
        return;
    }

    const targetCategory = currentSelectedAudioCategory || 'general';
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang tải MP3...';
    }

    try {
        const res = await fetch('/api/audio/download-yt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, category: targetCategory })
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`✅ Đã tải thành công: ${data.title}!`, 'success');
            if (input) input.value = '';
            loadAudioCategories();
        } else {
            showToast('Lỗi: ' + (data.detail || data.message || 'Lỗi khi tải từ YouTube'), 'error');
        }
    } catch (err) {
        showToast('Lỗi tải từ YouTube: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// --------------------------------------------------------------------------
// --- TÌM KIẾM YOUTUBE NO-COPYRIGHT AUDIO (SUB-VIEW 1) ---
// --------------------------------------------------------------------------

async function searchYouTubeAudio() {
    const kwInput = document.getElementById('audioSearchKeyword');
    const limitSelect = document.getElementById('audioSearchLimit');
    const btn = document.getElementById('btnSearchAudio');
    const tbody = document.getElementById('audioSearchResultsBody');

    const keyword = kwInput ? kwInput.value.trim() : '';
    const maxResults = limitSelect ? parseInt(limitSelect.value, 10) : 50;

    if (!keyword) {
        markInputError('audioSearchKeyword', 'Vui lòng nhập từ khóa tìm kiếm âm thanh!');
        return;
    }
    if (isNaN(maxResults) || maxResults < 1 || maxResults > 100) {
        markInputError('audioSearchLimit', 'Số lượng bài hát quét phải từ 1 đến 100!');
        return;
    }

    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang quét nhạc...';
    }
    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-5 text-muted"><i class="fa-solid fa-spinner fa-spin fa-2x mb-3 text-cyan"></i><br>Đang tìm kiếm nhạc No-Copyright trên YouTube...</td></tr>';

    try {
        const res = await fetch('/api/audio/search-youtube', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyword, max_results: maxResults })
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            rawAudioSearchResults = data.tracks || [];
            // Reset filters
            audioSortField = 'default';
            audioSortAsc = false;
            audioFilterDuration = 'all';
            audioFilterDownload = 'all';
            audioFilterKeyword = '';

            const sortSel = document.getElementById('audioSortSelect');
            if (sortSel) sortSel.value = 'default';
            const durSel = document.getElementById('audioFilterDurationSelect');
            if (durSel) durSel.value = 'all';
            const dlSel = document.getElementById('audioFilterDownloadSelect');
            if (dlSel) dlSel.value = 'all';
            const kwInp = document.getElementById('audioFilterKeywordInput');
            if (kwInp) kwInp.value = '';

            updateAudioSortDirectionBtn();
            updateAudioHeaderSortIcons();
            renderAudioSearchResults();
            showToast(`✅ Đã tìm thấy ${rawAudioSearchResults.length} bài hát No-Copyright!`, 'success');
        } else {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-5 text-danger">Lỗi khi tìm kiếm: ${escapeHtml(data.detail || data.message || 'Không xác định')}</td></tr>`;
            showToast('Lỗi tìm kiếm: ' + (data.detail || data.message || 'Không xác định'), 'error');
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-5 text-danger">Lỗi: ${escapeHtml(err.message)}</td></tr>`;
        showToast('Lỗi kết nối: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// Xử lý sắp xếp và bộ lọc kết quả tìm kiếm
function handleAudioSortChange(field) {
    audioSortField = field;
    if (field !== 'default') {
        if (['duration', 'view_count', 'upload_date'].includes(field)) {
            audioSortAsc = false;
        } else {
            audioSortAsc = true;
        }
    }
    updateAudioSortDirectionBtn();
    updateAudioHeaderSortIcons();
    renderAudioSearchResults();
}

function toggleAudioSortDirection() {
    audioSortAsc = !audioSortAsc;
    updateAudioSortDirectionBtn();
    updateAudioHeaderSortIcons();
    renderAudioSearchResults();
}

function handleAudioHeaderSort(field) {
    if (audioSortField === field) {
        audioSortAsc = !audioSortAsc;
    } else {
        audioSortField = field;
        if (['duration', 'view_count', 'upload_date'].includes(field)) {
            audioSortAsc = false;
        } else {
            audioSortAsc = true;
        }
    }
    const sortSel = document.getElementById('audioSortSelect');
    if (sortSel) sortSel.value = audioSortField;
    updateAudioSortDirectionBtn();
    updateAudioHeaderSortIcons();
    renderAudioSearchResults();
}

function updateAudioHeaderSortIcons() {
    const headers = [
        { id: 'th-audio-title', field: 'title' },
        { id: 'th-audio-uploader', field: 'uploader' },
        { id: 'th-audio-duration', field: 'duration' },
        { id: 'th-audio-views', field: 'view_count' },
        { id: 'th-audio-date', field: 'upload_date' }
    ];

    headers.forEach(h => {
        const th = document.getElementById(h.id);
        if (!th) return;
        const icon = th.querySelector('.sort-icon');
        if (audioSortField === h.field) {
            th.classList.add('sorted-active');
            if (icon) {
                icon.className = audioSortAsc
                    ? 'fa-solid fa-arrow-up-short-wide sort-icon'
                    : 'fa-solid fa-arrow-down-wide-short sort-icon';
            }
        } else {
            th.classList.remove('sorted-active');
            if (icon) icon.className = 'fa-solid fa-sort sort-icon';
        }
    });
}

function updateAudioSortDirectionBtn() {
    const icon = document.getElementById('audioSortDirIcon');
    const text = document.getElementById('audioSortDirText');
    if (audioSortAsc) {
        if (icon) icon.className = 'fa-solid fa-arrow-up-wide-short';
        if (text) text.textContent = 'Tăng dần';
    } else {
        if (icon) icon.className = 'fa-solid fa-arrow-down-wide-short';
        if (text) text.textContent = 'Giảm dần';
    }

    const btn = document.getElementById('btnAudioSortDirection');
    if (btn) {
        if (audioSortField === 'default') {
            btn.style.opacity = '0.45';
            btn.style.pointerEvents = 'none';
        } else {
            btn.style.opacity = '1';
            btn.style.pointerEvents = 'auto';
        }
    }
}

function handleAudioFilterDurationChange(val) {
    audioFilterDuration = val;
    renderAudioSearchResults();
}

function handleAudioFilterDownloadChange(val) {
    audioFilterDownload = val;
    renderAudioSearchResults();
}

function handleAudioFilterKeywordChange(val) {
    audioFilterKeyword = val.toLowerCase().trim();
    renderAudioSearchResults();
}

// Render bảng kết quả tìm kiếm YouTube
function renderAudioSearchResults() {
    const tbody = document.getElementById('audioSearchResultsBody');
    const countEl = document.getElementById('audioSearchResultsCount');
    if (!tbody) return;

    if (!rawAudioSearchResults.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center py-5 text-muted">Không tìm thấy bài hát nào phù hợp.</td></tr>';
        if (countEl) countEl.textContent = '0 Bài Hát';
        return;
    }

    // 1. Filter
    let list = rawAudioSearchResults.filter(item => {
        // Duration filter
        if (audioFilterDuration === 'short' && item.duration >= 120) return false;
        if (audioFilterDuration === 'medium' && (item.duration < 120 || item.duration > 300)) return false;
        if (audioFilterDuration === 'long' && item.duration <= 300) return false;

        // Download status filter
        if (audioFilterDownload === 'downloaded' && !item.is_downloaded) return false;
        if (audioFilterDownload === 'not_downloaded' && item.is_downloaded) return false;

        // Keyword filter
        if (audioFilterKeyword) {
            const text = `${item.title} ${item.uploader}`.toLowerCase();
            if (!text.includes(audioFilterKeyword)) return false;
        }
        return true;
    });

    // 2. Sort
    if (audioSortField !== 'default') {
        list.sort((a, b) => {
            let va = a[audioSortField];
            let vb = b[audioSortField];
            if (typeof va === 'string') {
                return audioSortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
            }
            return audioSortAsc ? (va - vb) : (vb - va);
        });
    }

    if (countEl) countEl.textContent = `${list.length} / ${rawAudioSearchResults.length} Bài`;

    if (!list.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">Không có bài nào thỏa mãn bộ lọc hiện tại.</td></tr>';
        return;
    }

    tbody.innerHTML = list.map((item, idx) => {
        const btnId = `btnPlayYt_${idx}`;
        const escapedTitle = escapeHtml(item.title).replace(/'/g, "\\'");
        const escapedUrl = escapeHtml(item.url).replace(/'/g, "\\'");
        const isDownloadedBadge = item.is_downloaded
            ? '<span class="badge badge-success" style="font-size:10px;"><i class="fa-solid fa-check"></i> Đã có trong kho</span>'
            : '';

        return `
            <tr>
                <td data-col="col-title">
                    <div style="display:flex; align-items:center; gap:12px; min-width:0;">
                        <img src="${escapeHtml(item.thumbnail)}" alt="Thumb" class="audio-thumb-img" onerror="this.src='/logo/app-logo.png'">
                        <div style="display:flex; flex-direction:column; gap:2px; min-width:0;">
                            <div class="table-text-truncate" style="font-weight:600; color:#fff; max-width:250px;" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
                            ${isDownloadedBadge}
                        </div>
                    </div>
                </td>
                <td>
                    <div class="table-text-truncate" style="max-width:160px;" title="${escapeHtml(item.uploader)}">
                        <i class="fa-brands fa-youtube text-danger" style="margin-right:4px;"></i>
                        ${escapeHtml(item.uploader)}
                    </div>
                </td>
                <td><span class="badge badge-secondary">${item.duration_string}</span></td>
                <td>${item.views_formatted}</td>
                <td>${escapeHtml(item.upload_date || '--')}</td>
                <td class="text-center">
                    <button type="button" class="audio-preview-btn has-tooltip" id="${btnId}"
                        onclick="togglePlayAudioPreview('${escapeHtml(item.url)}', '${btnId}', '${escapedTitle}', '${escapeHtml(item.thumbnail)}', '${item.id}')"
                        data-tooltip="Bấm để Nghe Thử">
                        <i class="fa-solid fa-play"></i>
                    </button>
                </td>
                <td class="text-center">
                    <button type="button" class="btn btn-sm btn-primary has-tooltip tooltip-side-left"
                        onclick="openDownloadAudioCategoryModal('${escapedUrl}', '${item.id}', '${escapedTitle}')"
                        data-tooltip="Tải MP3 vào Playlist">
                        <i class="fa-solid fa-cloud-arrow-down"></i> Tải Về
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

// Modal Chọn Playlist để tải từ kết quả tìm kiếm YouTube
function openDownloadAudioCategoryModal(url, id, title, isManualUrl = false) {
    const urlInputGroup = document.getElementById('downloadAudioUrlInputGroup');
    const customUrlInput = document.getElementById('downloadAudioTrackCustomUrl');
    const hiddenUrlInput = document.getElementById('downloadAudioTrackUrl');
    const hiddenIdInput = document.getElementById('downloadAudioTrackId');
    const subTitle = document.getElementById('downloadAudioTrackTitleSub');

    if (hiddenUrlInput) hiddenUrlInput.value = url || '';
    if (hiddenIdInput) hiddenIdInput.value = id || '';

    if (isManualUrl) {
        if (urlInputGroup) urlInputGroup.style.display = 'block';
        if (customUrlInput) {
            customUrlInput.value = url || '';
            setTimeout(() => customUrlInput.focus(), 100);
        }
        if (subTitle) {
            subTitle.textContent = 'Dán link YouTube để tự động bóc tách MP3 vào Playlist';
            subTitle.title = 'Dán link YouTube để tự động bóc tách MP3 vào Playlist';
        }
    } else {
        if (urlInputGroup) urlInputGroup.style.display = 'none';
        if (subTitle) {
            subTitle.textContent = title || 'Đang chọn bài hát...';
            subTitle.title = title || '';
        }
    }

    // Nạp danh sách categories vào dropdown
    const select = document.getElementById('downloadAudioTargetCategorySelect');
    if (select) {
        if (!cachedAudioCategories.length) {
            select.innerHTML = '<option value="general">Nhạc Nền Tổng Hợp (general)</option>';
        } else {
            select.innerHTML = cachedAudioCategories.map(c => `
                <option value="${escapeHtml(c.id)}" ${c.id === currentSelectedAudioCategory ? 'selected' : ''}>
                    ${escapeHtml(c.display_name || c.name)} (${c.track_count} bài)
                </option>
            `).join('');
        }
    }

    document.getElementById('modalDownloadAudioCategory').classList.add('active');
}

function closeDownloadAudioCategoryModal() {
    document.getElementById('modalDownloadAudioCategory').classList.remove('active');
}

async function confirmDownloadAudioTrack(btn) {
    const urlInputGroup = document.getElementById('downloadAudioUrlInputGroup');
    const isManual = urlInputGroup && urlInputGroup.style.display !== 'none';
    const targetInputId = isManual ? 'downloadAudioTrackCustomUrl' : 'downloadAudioTrackUrl';
    const rawUrl = (document.getElementById(targetInputId)?.value || '').trim();

    if (!rawUrl) {
        markInputError(targetInputId, 'Vui lòng nhập link YouTube cần tải MP3!');
        return;
    }
    if (!isValidYouTubeUrl(rawUrl)) {
        markInputError(targetInputId, 'Link YouTube không đúng định dạng!');
        return;
    }

    const targetCategory = document.getElementById('downloadAudioTargetCategorySelect')?.value || 'general';
    const videoId = document.getElementById('downloadAudioTrackId')?.value;

    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang tải MP3...';
    }

    try {
        const res = await fetch('/api/audio/download-yt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: rawUrl, category: targetCategory })
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            showToast(`✅ Đã tải thành công "${data.title || 'bài hát'}" vào [${targetCategory}]!`, 'success');
            closeDownloadAudioCategoryModal();

            // Đánh dấu is_downloaded = true trong bảng kết quả nếu có videoId
            if (videoId) {
                const item = rawAudioSearchResults.find(x => x.id === videoId);
                if (item) item.is_downloaded = true;
                renderAudioSearchResults();
            }

            // Cập nhật lại thư viện nếu đang mở
            loadAudioCategories();
        } else {
            showToast('Lỗi: ' + (data.detail || data.message || 'Lỗi khi tải bài hát'), 'error');
        }
    } catch (err) {
        showToast('Lỗi tải bài hát: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

// --------------------------------------------------------------------------
// --- TÍCH HỢP CÀI ĐẶT BGM VÀO KÊNH, STUDIO & CHIẾN DỊCH ---
// --------------------------------------------------------------------------

function populateAllBgmSelects(categories) {
    const cats = categories || cachedAudioCategories || [];

    const makeOptions = (defaultLabel, currentVal, includeInherit = false) => {
        let html = `<option value="">${escapeHtml(defaultLabel)}</option>`;
        if (includeInherit) {
            const isInherit = currentVal === 'inherit' ? 'selected' : '';
            html += `<option value="inherit" ${isInherit}>-- Theo cài đặt BGM của từng Kênh nguồn --</option>`;
        }
        cats.forEach(c => {
            const isSel = c.id === currentVal ? 'selected' : '';
            html += `<option value="${escapeHtml(c.id)}" ${isSel}>${escapeHtml(c.display_name || c.name)} (${c.track_count || 0} bài)</option>`;
        });
        return html;
    };

    // 1. Modal Kênh YouTube
    const chSel = document.getElementById('settingBgmFolder');
    if (chSel) {
        const val = chSel.value;
        chSel.innerHTML = makeOptions('-- Không Dùng Nhạc Nền --', val, false);
    }

    // 2. Video Studio Recipe
    const stSel = document.getElementById('studioBgmFolder');
    if (stSel) {
        const val = stSel.value;
        stSel.innerHTML = makeOptions('-- Tắt / Không Dùng Nhạc Nền --', val, false);
    }

    // 3. New Campaign Modal
    const newCampSel = document.getElementById('campaignBgmFolder');
    if (newCampSel) {
        const val = newCampSel.value;
        newCampSel.innerHTML = makeOptions('-- Tắt / Không Dùng Nhạc Nền --', val, true);
    }

    // 4. Edit Campaign Modal
    const editCampSel = document.getElementById('editCampaignBgmFolder');
    if (editCampSel) {
        const val = editCampSel.value;
        editCampSel.innerHTML = makeOptions('-- Tắt / Không Dùng Nhạc Nền --', val, true);
    }
}

async function populateChannelBgmSelect(selectedFolder, selectedVolume) {
    const select = document.getElementById('settingBgmFolder');
    const volInput = document.getElementById('settingBgmVolume');
    const volLabel = document.getElementById('settingBgmVolumeVal');

    if (volInput) volInput.value = selectedVolume != null ? selectedVolume : 0.15;
    if (volLabel) volLabel.textContent = Math.round((selectedVolume != null ? selectedVolume : 0.15) * 100) + '%';

    try {
        if (!cachedAudioCategories.length) {
            const res = await fetch('/api/audio/categories');
            const data = await res.json();
            if (data.status === 'success') cachedAudioCategories = data.categories || [];
        }

        populateAllBgmSelects(cachedAudioCategories);
        if (select && selectedFolder) {
            select.value = selectedFolder;
        }
    } catch (err) {
        console.error('Lỗi populate BGM categories cho kênh:', err);
    }
}

// Khởi tạo kéo thả Upload file khi tài liệu sẵn sàng
document.addEventListener('DOMContentLoaded', () => {
    const dropzone = document.getElementById('audioUploadDropzone');
    if (dropzone) {
        ['dragenter', 'dragover'].forEach(eventName => {
            dropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.add('dragover');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove('dragover');
            }, false);
        });

        dropzone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            handleAudioFilesSelected(files);
        }, false);
    }
});

