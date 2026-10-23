// State
let currentTab = 'tab-auto-pipeline';
let cachedGpmProfiles = [];
let cachedVideos = [];
let cachedCampaigns = [];
let activeStudioVideo = null;
let currentStudioFilter = 'all';

// DOM Ready
document.addEventListener('DOMContentLoaded', () => {
    setupNavigation();
    loadDashboardStats();
    loadGpmProfiles();
    loadVideos();
    loadSavedChannels();
    loadCampaigns();
    loadPipelineStatus();
    loadSchedulerSettings();
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

    const schedModal = document.getElementById('schedulerSettingsModal');
    if (schedModal) {
        schedModal.addEventListener('click', (e) => {
            if (e.target === schedModal) {
                closeSchedulerSettingsModal();
            }
        });
    }

    // Keyboard ESC listener for modals
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeAllActionMenus();
            closeChannelDetailModal();
            closeNewCampaignModal();
            closeSchedulerSettingsModal();
        }
    });

    const btnSaveDetail = document.getElementById('btnToggleSaveFromDetail');
    if (btnSaveDetail) {
        btnSaveDetail.addEventListener('click', toggleSaveFromDetailModal);
    }

    // Auto refresh logs & stats every 8 seconds
    setInterval(loadDashboardStats, 8000);
});

// Toast notification helper
function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.style.borderColor = isError ? 'rgba(239, 68, 68, 0.5)' : 'rgba(16, 185, 129, 0.5)';
    toast.classList.add('show');
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3500);
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
            title: 'Chiến Dịch Tự Động Hóa (Auto-Pilot Hub)',
            sub: 'Chuỗi tự động hóa: Quét RSS Kênh → Tải MP4 → AI Render 9:16 Beta → Tự Đăng Lên TikTok GPM'
        },
        'tab-video-studio': {
            title: 'Studio & Công Thức Biên Tập Video 9:16',
            sub: 'Tùy chỉnh mẫu cắt >60s chuẩn Quỹ Beta, lách bản quyền & xem trước trên mô phỏng điện thoại'
        },
        'tab-sources': {
            title: 'Quản Lý Kênh YouTube Nguồn',
            sub: 'Theo dõi RSS feed các kênh chất lượng cao và quét từ khóa tìm kênh mới'
        },
        'tab-gpm-farm': {
            title: 'Dàn Tài Khoản GPMLogin & Mốc 10K Follow',
            sub: 'Quản lý profiles TikTok, theo dõi tăng trưởng follower và cấu hình báo động Telegram'
        },
        'tab-overview': {
            title: 'Bảng Điều Khiển Tổng Quan',
            sub: 'Thống kê tổng quan hệ thống, tài nguyên và tiến độ tăng trưởng'
        },
        'tab-pipeline-queue': {
            title: 'Hàng Đợi & Lịch Đăng (Kanban Pipeline)',
            sub: 'Theo dõi 4 công đoạn: Mới Tải Về → Đã Render 9:16 → Chờ Giờ Đăng → Đã Đăng'
        },
        'tab-logs': {
            title: 'Nhật Ký Hoạt Động Hệ Thống',
            sub: 'Toàn bộ sự kiện, thông tin background và cảnh báo lỗi thời gian thực'
        },
        'tab-settings': {
            title: 'Cài Đặt API Keys & Cấu Hình',
            sub: 'Cấu hình YouTube Data API, OpenAI, Gemini và Telegram Alert Bot'
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
    } else if (tabId === 'tab-pipeline-queue') {
        loadPipelineStatus();
    } else if (tabId === 'tab-settings') {
        loadApiKeySettings();
        loadSchedulerSettings();
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
    } catch (e) {}
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
    const keyword = document.getElementById('ytSearchKeyword').value.trim();
    const maxResults = parseInt(document.getElementById('ytMaxResults').value, 10);
    const tbody = document.getElementById('ytChannelsBody');
    const toolbar = document.getElementById('ytTableToolbar');
    const btn = document.getElementById('btnSearchYt');

    if (!keyword) {
        showToast('Vui lòng nhập từ khóa ngách!', true);
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

function renderYtChannelsTable() {
    const tbody = document.getElementById('ytChannelsBody');
    const countBadge = document.getElementById('ytResultCountBadge');

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

        const handleText = c.handle ? `<span style="font-size:11px; color:var(--accent-cyan); font-weight:500;">${escapeHtml(c.handle)}</span>` : '';
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
                        <button type="button" class="action-dropdown-item" onclick="toggleSaveFromMenu(${c.originalIndex})">
                            <i class="fa-solid ${c.is_saved ? 'fa-bookmark-slash text-danger' : 'fa-bookmark text-gold'}"></i> 
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
            } catch (e) {}
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
            } catch (e) {}
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
        } catch (e) {}
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
    const url = document.getElementById('directDownloadUrl').value.trim();
    const btn = document.getElementById('btnDownloadVideo');
    if (!url) {
        showToast('Hãy nhập link video YouTube!', true);
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
            body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Tải video thành công!');
            document.getElementById('directDownloadUrl').value = '';
            loadVideos();
            loadStudioVideos();
            loadDashboardStats();
        } else {
            showToast('Lỗi: ' + (data.detail || 'Không xác định'), true);
        }
    } catch (err) {
        showToast('Lỗi tải video: ' + err.message, true);
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
                    <strong>${escapeHtml(v.title)}</strong><br>
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

async function loadGpmProfiles() {
    const tbody = document.getElementById('gpmTableBody');
    const eligibleGrid = document.getElementById('eligibleCardsGrid');

    try {
        const res = await fetch('/api/gpm/profiles');
        const profiles = await res.json();
        cachedGpmProfiles = profiles;

        if (profiles.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-muted">Chưa có profile nào. Hãy ấn nút "Đồng Bộ GPM" ở góc trên!</td></tr>`;
            return;
        }

        tbody.innerHTML = profiles.map(p => `
            <tr>
                <td><strong>${escapeHtml(p.name)}</strong></td>
                <td><code>${escapeHtml(p.raw_proxy || 'Direct IP')}</code></td>
                <td>@${escapeHtml(p.tiktok_username || 'Chưa gắn')}</td>
                <td><strong style="color:var(--accent-cyan);">${(p.followers_count || 0).toLocaleString()}</strong></td>
                <td>${(p.total_views || 0).toLocaleString()}</td>
                <td>
                    ${p.eligible_10k
                ? '<span class="badge badge-success"><i class="fa-solid fa-trophy"></i> ĐỦ ĐIỀU KIỆN BETA!</span>'
                : '<span class="badge badge-info">Đang Nuôi</span>'}
                </td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="simulateUpdateStats('${p.gpm_id}')">
                        <i class="fa-solid fa-pen-to-square"></i> Cập Nhật Follow
                    </button>
                </td>
            </tr>
        `).join('');

        // Cập nhật tab 10k follower
        const eligibleList = profiles.filter(p => p.eligible_10k === 1);
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
                        <p><strong>Followers:</strong> <span style="color:white; font-size:16px; font-weight:700;">${e.followers_count.toLocaleString()}</span></p>
                        <p><strong>Profile GPM:</strong> ${escapeHtml(e.name)}</p>
                        <p><strong>Proxy:</strong> ${escapeHtml(e.raw_proxy || 'Direct')}</p>
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
    } catch (err) {
        console.error('Lỗi nạp profiles:', err);
    }
}

async function simulateUpdateStats(gpmId) {
    const followers = prompt("Nhập số follower mới cho profile này:", "10250");
    if (!followers) return;

    try {
        await fetch('/api/profiles/stats', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                gpm_id: gpmId,
                followers: parseInt(followers, 10),
                views: 150000,
                username: "mmo_beta_us"
            })
        });
        showToast("Đã cập nhật chỉ số profile!");
        loadGpmProfiles();
        loadDashboardStats();
    } catch (err) {
        showToast("Lỗi cập nhật: " + err.message, true);
    }
}

// 5. Upload Modal
function openUploadModal(videoId) {
    const video = cachedVideos.find(v => v.id == videoId);
    if (!video || !video.rendered_path) {
        showToast('Video chưa được render AI!', true);
        return;
    }

    const select = document.getElementById('modalProfileSelect');
    if (cachedGpmProfiles.length === 0) {
        showToast('Vui lòng đồng bộ danh sách GPMLogin trước!', true);
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
    const profileId = document.getElementById('modalProfileSelect').value;
    const videoPath = document.getElementById('modalVideoPath').value;
    const title = document.getElementById('modalVideoTitle').value;
    const tags = document.getElementById('modalVideoTags').value;

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
        if (data.success) {
            showToast('Đã thực hiện xong lệnh đăng video lên TikTok!');
            closeUploadModal();
        } else {
            showToast('Lỗi: ' + data.message, true);
        }
    } catch (err) {
        showToast('Lỗi kết nối upload: ' + err.message, true);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Bắt Đầu Đăng Bài';
    }
}

// 6. Test Telegram Alert
async function testTelegramAlert(btn) {
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Gửi...';
    }
    showToast('Đang gửi tin nhắn thử nghiệm tới Telegram...');
    try {
        const res = await fetch('/api/telegram/test-alert', { method: 'POST' });
        const data = await res.json();
        showToast(data.message);
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

function renderSavedChannelsTable() {
    const tbody = document.getElementById('savedChannelsBody');
    if (!tbody) return;

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

    const badgeCount = document.getElementById('badgeSavedCount');
    if (badgeCount) badgeCount.textContent = `${list.length}/${cachedSavedChannels.length} Kênh`;

    // Update Header Sort Icons
    ['title', 'country', 'subscriber_count', 'video_count', 'avg_views', 'days_since_last_upload', 'upload_cadence_days', 'is_active'].forEach(f => {
        const thMap = {
            'title': 'th-saved-title',
            'country': 'th-saved-country',
            'subscriber_count': 'th-saved-subs',
            'video_count': 'th-saved-videos',
            'avg_views': 'th-saved-avg-views',
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
        tbody.innerHTML = `<tr><td colspan="11" class="text-center py-4 text-muted"><i class="fa-solid fa-folder-open" style="font-size: 24px; opacity: 0.3; display: block; margin-bottom: 8px;"></i>Không tìm thấy kênh nào phù hợp.</td></tr>`;
        return;
    }

    tbody.innerHTML = list.map(c => {
        const cid = c.channel_id || '';
        const hasDisplayName = c.display_name && c.display_name.trim();
        const displayTitle = hasDisplayName ? escapeHtml(c.display_name) : escapeHtml(c.title || cid);
        const origTitle = hasDisplayName ? `<span class="channel-title-main" style="opacity:0.75; font-size:11px;">Gốc: ${escapeHtml(c.title)}</span>` : '';
        const aliasTag = hasDisplayName ? `<span class="channel-alias-tag"><i class="fa-solid fa-tag"></i> Tên riêng</span>` : '';

        const handleText = c.handle ? `<span style="font-size:11px; color:var(--accent-cyan); font-weight:500;">@${escapeHtml(c.handle.replace('@', ''))}</span>` : '';
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
            ratioBadge = `<div class="badge-ratio ${ratioClass}" style="margin-top:2px;">Ratio: ${ratio.toFixed(2)}x</div>`;
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
                    ${ratioBadge}
                </td>

                <!-- Col 5: Tổng Video -->
                <td>
                    <div style="font-size:12.5px; color:#cbd5e1;">${c.video_count ? c.video_count.toLocaleString() : 'N/A'}</div>
                </td>

                <!-- Col 6: Lượt Xem TB -->
                <td>
                    <div style="font-weight:700; color:#fff; font-size:13px;">${c.avg_views ? formatNumber(c.avg_views) : '<span class="text-muted">N/A</span>'}</div>
                </td>

                <!-- Col 7: Video Mới Nhất -->
                <td><span style="font-size:12px; color:#cbd5e1;">${lastUploadText}</span></td>

                <!-- Col 8: Tần Suất Đăng -->
                <td><span class="badge badge-purple">${cadenceDesc}</span></td>

                <!-- Col 9: Video (Tải / Render) -->
                <td>
                    <div style="display:flex; gap:4px; flex-wrap:wrap;">
                        <span class="badge badge-blue" title="Video đã tải"><i class="fa-solid fa-download"></i> ${dlCount}</span>
                        <span class="badge badge-gold" title="Video đã render AI"><i class="fa-solid fa-wand-magic-sparkles"></i> ${rdCount}</span>
                    </div>
                </td>

                <!-- Col 10: Trạng Thái Toggle -->
                <td>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <label class="switch" title="${isActive ? 'Bấm để Tạm ngưng (Dừng tải và render)' : 'Bấm để Bật Hoạt động (Tự động tải và render)'}">
                            <input type="checkbox" ${isActive ? 'checked' : ''} onchange="toggleChannelStatusInline('${escapeHtml(cid)}', this)">
                            <span class="slider round"></span>
                        </label>
                        ${statusBadge}
                    </div>
                </td>

                <!-- Col 11: Thao Tác -->
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
    if (!confirm('Bạn có chắc muốn BỎ LƯU và ngừng theo dõi kênh này?')) return;

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
    document.getElementById('settingDisplayName').value = channel.display_name || '';
    document.getElementById('settingCustomProxy').value = channel.custom_proxy || '';
    document.getElementById('settingDownloadDir').value = channel.download_dir || '';
    document.getElementById('settingRenderDir').value = channel.render_dir || '';
    document.getElementById('settingIsActive').checked = channel.is_active === 1;
    document.getElementById('settingAutoDownload').checked = channel.auto_download === 1;
    document.getElementById('settingAutoRender').checked = channel.auto_render === 1;

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
    const channelId = document.getElementById('settingChannelId').value;
    if (!channelId) return;

    const payload = {
        channel_id: channelId,
        display_name: document.getElementById('settingDisplayName').value.trim(),
        custom_proxy: document.getElementById('settingCustomProxy').value.trim(),
        download_dir: document.getElementById('settingDownloadDir').value.trim(),
        render_dir: document.getElementById('settingRenderDir').value.trim(),
        is_active: document.getElementById('settingIsActive').checked ? 1 : 0,
        auto_download: document.getElementById('settingAutoDownload').checked ? 1 : 0,
        auto_render: document.getElementById('settingAutoRender').checked ? 1 : 0
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
        if (data.status === 'success') {
            showToast('Đã lưu cấu hình kênh thành công!');
            closeChannelSettingsModal();
            loadSavedChannels();
        } else {
            showToast('Lỗi khi lưu: ' + (data.message || 'Thất bại'), true);
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

async function clearChannelHistoryFromModal(btn) {
    if (!activeModalChannel) return;
    const cid = activeModalChannel.channel_id;
    const name = activeModalChannel.display_name || activeModalChannel.title;

    if (!confirm(`Bạn có chắc muốn XÓA TOÀN BỘ lịch sử video đã tải và render của kênh "${name}"? Thao tác này cũng sẽ xóa các tệp tin trên đĩa!`)) {
        return;
    }

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

    if (!confirm(`Xác nhận xóa hoàn toàn kênh "${name}" khỏi cơ sở dữ liệu theo dõi?`)) {
        return;
    }

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
async function loadPipelineStatus() {
    try {
        const res = await fetch('/api/pipeline/status');
        const data = await res.json();

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
                            <td><strong>${escapeHtml(v.title || 'Video #' + v.id)}</strong></td>
                            <td><span class="badge badge-cyan">${escapeHtml(v.channel_name || 'Kênh ngoài')}</span></td>
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
    const scheduled = uploadTasks.filter(t => t.status === 'queued' || t.status === 'processing');
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
        colSc.innerHTML = scheduled.length ? scheduled.map(t => `
            <div class="kanban-task-card">
                <strong style="font-size:12px; color:#fff;">${escapeHtml(t.title || 'Task #' + t.id)}</strong>
                <div style="font-size:11px; color:var(--accent-gold);">
                    <i class="fa-solid fa-robot"></i> ${escapeHtml(t.gpm_profile_name || 'GPM Profile')}
                </div>
                <div style="font-size:10px; color:var(--text-muted);">
                    Hẹn giờ: ${escapeHtml(t.scheduled_time || 'Đang chờ')}
                </div>
            </div>
        `).join('') : '<div class="text-center py-4 text-muted" style="font-size:11px;">Không có video lên lịch</div>';
    }
    if (colUp) {
        colUp.innerHTML = uploaded.length ? uploaded.map(t => `
            <div class="kanban-task-card">
                <strong style="font-size:12px; color:#fff;">${escapeHtml(t.title || 'Task #' + t.id)}</strong>
                <div style="font-size:11px; color:var(--accent-green);">
                    <i class="fa-brands fa-tiktok"></i> ${escapeHtml(t.gpm_profile_name || 'GPM')}
                </div>
                <div style="font-size:10px; color:var(--text-muted);">${escapeHtml(t.uploaded_at || 'Đã hoàn tất')}</div>
            </div>
        `).join('') : '<div class="text-center py-4 text-muted" style="font-size:11px;">Chưa có bài đăng</div>';
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
                        <h4 style="margin:0; font-size:15px; color:#fff;">${escapeHtml(c.name)}</h4>
                        ${distBadge}
                        ${freqBadge}
                        ${warmupBadge}
                    </div>
                    <div style="display:flex; gap:8px;">
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
                            <p>${c.video_duration || 65}s Beta • Speed x${c.speed_factor} • ${c.flip_horizontal ? 'Lật hình' : 'Gốc'}</p>
                            <div style="margin-top:3px;">${subBadge}</div>
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
                        </div>
                    </div>
                </div>

                <div class="campaign-footer-row">
                    <span><i class="fa-regular fa-calendar"></i> Tạo lúc: ${escapeHtml(c.created_at || '')}</span>
                    <span style="color:var(--accent-cyan);"><i class="fa-solid fa-bolt"></i> Phân phối: ${chCount} kênh &rarr; ${gpmCount} nick GPM (${c.distribution_mode === 'round_robin' ? 'Xoay vòng không trùng clip' : 'Chia đều'})</span>
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
    } catch (_) {}
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

    // 1. Gather Selected Channels
    const chBoxes = document.querySelectorAll('.campaign-ch-check:checked');
    const selectedChannelIds = Array.from(chBoxes).map(b => b.value);
    if (selectedChannelIds.length === 0) {
        showToast('⚠️ Vui lòng chọn ít nhất 1 kênh YouTube nguồn (hoặc chọn nhiều kênh 1, 2, 3...)!', true);
        return;
    }

    // 2. Gather Selected GPM Profiles
    const gpmBoxes = document.querySelectorAll('.campaign-gpm-check:checked');
    const selectedGpmIds = Array.from(gpmBoxes).map(b => parseInt(b.value, 10)).filter(id => !isNaN(id));
    if (selectedGpmIds.length === 0) {
        showToast('⚠️ Vui lòng chọn ít nhất 1 Profile GPMLogin nhận video (hoặc chọn nhóm nick a, b, c...)!', true);
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Kích Hoạt...';
    }

    // Gather frequency & advanced options
    const freq = document.getElementById('campaignFrequencySelect')?.value || 'daily';
    let intervalDays = 1;
    if (freq === 'every_2_days') intervalDays = 2;
    else if (freq === 'every_3_days') intervalDays = 3;
    else if (freq === 'custom_interval') {
        intervalDays = parseInt(document.getElementById('campaignCustomIntervalInput')?.value, 10) || 2;
    }

    const dowBoxes = document.querySelectorAll('.campaign-dow-check:checked');
    const daysOfWeek = Array.from(dowBoxes).map(b => b.value).join(',');
    const randomDelay = parseInt(document.getElementById('campaignRandomDelaySelect')?.value, 10) || 10;
    const warmup = document.getElementById('campaignWarmupSwitch')?.checked ? 1 : 0;

    const payload = {
        name: document.getElementById('campaignNameInput').value.trim() || `Chiến Dịch Auto ${selectedChannelIds.length} Kênh -> ${selectedGpmIds.length} Nick`,
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
        subtitle_enabled: document.getElementById('campaignSubtitleSwitch')?.checked ? 1 : 0,
        subtitle_style: document.getElementById('campaignSubtitleStyle')?.value || 'karaoke_yellow',
        speed_factor: document.getElementById('campaignSpeedSwitch')?.checked ? 1.03 : 1.0,
        flip_horizontal: document.getElementById('campaignFlipSwitch')?.checked ? 1 : 0,
        daily_limit: parseInt(document.getElementById('campaignDailyLimitInput')?.value, 10) || 3,
        post_schedule: document.getElementById('campaignScheduleInput')?.value.trim() || '11:30, 18:00, 20:30',
        post_frequency: freq,
        post_interval_days: intervalDays,
        post_days_of_week: daysOfWeek || 'mon,tue,wed,thu,fri,sat,sun',
        random_delay_minutes: randomDelay,
        warmup_mode: warmup,
        is_active: 1
    };

    try {
        const res = await fetch('/api/campaigns', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(`✅ Đã tạo chiến dịch tự động thành công! (${selectedChannelIds.length} kênh &rarr; ${selectedGpmIds.length} nick TikTok)`);
            closeNewCampaignModal();
            loadCampaigns();
            loadPipelineStatus();
        } else {
            showToast('Lỗi: ' + (data.detail || 'Không thể tạo chiến dịch'), true);
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, true);
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
    if (!confirm('Bạn có chắc chắn muốn xóa chiến dịch tự động này?')) return;
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
// 10. VIDEO STUDIO & RECIPE LOGIC
// ==========================================
async function loadStudioVideos() {
    const listEl = document.getElementById('studioVideoList');
    const badge = document.getElementById('studioVideoCountBadge');
    try {
        const res = await fetch('/api/video/list');
        const videos = await res.json();
        cachedVideos = videos;
        if (badge) badge.textContent = `${videos.length} Video`;

        renderStudioVideoList();

        // If no active video selected, pick the first video
        if (!activeStudioVideo && videos.length > 0) {
            selectStudioVideo(videos[0].yt_video_id || videos[0].id);
        }
    } catch (err) {
        console.error('Lỗi nạp video studio:', err);
    }
}

function filterStudioVideos(filter) {
    currentStudioFilter = filter;
    document.getElementById('btnFilterAllVideos')?.classList.toggle('active', filter === 'all');
    document.getElementById('btnFilterOriginalVideos')?.classList.toggle('active', filter === 'original');
    document.getElementById('btnFilterRenderedVideos')?.classList.toggle('active', filter === 'rendered');
    renderStudioVideoList();
}

function renderStudioVideoList() {
    const listEl = document.getElementById('studioVideoList');
    if (!listEl) return;

    let filtered = cachedVideos;
    if (currentStudioFilter === 'original') {
        filtered = cachedVideos.filter(v => v.status !== 'rendered');
    } else if (currentStudioFilter === 'rendered') {
        filtered = cachedVideos.filter(v => v.status === 'rendered');
    }

    if (!filtered.length) {
        listEl.innerHTML = `<div class="text-center py-4 text-muted" style="font-size:12px;">Không có video phù hợp. Dán link phía trên để tải ngay!</div>`;
        return;
    }

    listEl.innerHTML = filtered.map(v => {
        const isSelected = activeStudioVideo && (activeStudioVideo.id === v.id || activeStudioVideo.yt_video_id === v.yt_video_id);
        const isRendered = v.status === 'rendered';

        return `
            <div class="studio-video-card ${isSelected ? 'selected' : ''}" onclick="selectStudioVideo('${v.yt_video_id || v.id}')">
                <div class="svc-title">${escapeHtml(v.title || 'Video #' + v.id)}</div>
                <div class="svc-meta">
                    <span><i class="fa-solid fa-clock"></i> ${v.duration || 65}s</span>
                    ${isRendered 
                        ? '<span class="badge badge-success" style="font-size:10px;"><i class="fa-solid fa-check"></i> Đã Có 9:16</span>'
                        : '<span class="badge badge-warning" style="font-size:10px;">Gốc</span>'}
                </div>
            </div>
        `;
    }).join('');
}

function selectStudioVideo(videoId) {
    const v = cachedVideos.find(item => item.id == videoId || item.yt_video_id === videoId);
    if (!v) return;
    activeStudioVideo = v;

    renderStudioVideoList();

    // Update active video info bar
    const titleEl = document.getElementById('studioActiveVideoTitle');
    const metaEl = document.getElementById('studioActiveVideoMeta');
    const hiddenId = document.getElementById('studioActiveYtVideoId');

    if (titleEl) titleEl.textContent = v.title || `Video #${v.id}`;
    if (metaEl) metaEl.textContent = `Thời lượng: ${v.duration || 65}s • Kênh: ${v.channel_name || 'Ngoại'} • Trạng thái: ${v.status}`;
    if (hiddenId) hiddenId.value = v.yt_video_id || v.id;

    // Update Phone Mockup Overlay
    const captionEl = document.getElementById('ttOverlayCaption');
    const partBadge = document.getElementById('ttOverlayPartBadge');
    if (captionEl) {
        captionEl.textContent = (v.ai_title || v.title || 'Video ngắn viral TikTok Beta') + ' ' + (v.ai_tags || '#fyp #xuhuong');
    }
    if (partBadge) {
        partBadge.textContent = v.status === 'rendered' ? 'PART 1 (9:16)' : 'VIDEO GỐC';
    }

    // Update Video Player Source
    const player = document.getElementById('studioVideoPlayer');
    const source = document.getElementById('studioVideoSource');
    if (player && source) {
        if (v.media_url) {
            source.src = v.media_url;
            player.load();
        } else {
            source.src = '';
        }
    }
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

async function renderStudioActiveVideo(btn) {
    if (!activeStudioVideo) {
        showToast('Vui lòng chọn 1 video từ danh sách bên trái trước!', true);
        return;
    }

    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Render AI 9:16...';
    }

    const duration = parseInt(document.getElementById('studioDurationRange')?.value) || 65;
    const flip = document.getElementById('studioFlipHorizontal')?.checked ?? true;
    const speed = document.getElementById('studioSpeedFactor')?.checked ? 1.03 : 1.0;

    showToast(`Bắt đầu render video 9:16 (Part 65s, speed ${speed}x)...`);

    try {
        const res = await fetch('/api/video/render', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                video_id: activeStudioVideo.yt_video_id,
                duration: duration,
                flip_horizontal: flip,
                speed_factor: speed
            })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Render AI 9:16 thành công! Bạn có thể xem thử trên mô phỏng điện thoại.');
            await loadStudioVideos();
            selectStudioVideo(activeStudioVideo.yt_video_id);
            loadDashboardStats();
            loadPipelineStatus();
        } else {
            showToast('Lỗi render: ' + (data.detail || 'Không xác định'), true);
        }
    } catch (err) {
        showToast('Lỗi render: ' + err.message, true);
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

        const gemEl = document.getElementById('settingGeminiKey');
        if (gemEl) gemEl.value = data.gemini_api_key || '';

        const oaiEl = document.getElementById('settingOpenAiKey');
        if (oaiEl) oaiEl.value = data.openai_api_key || '';

        const tgEl = document.getElementById('settingTelegramToken');
        if (tgEl) tgEl.value = data.telegram_bot_token || '';

        const tgChatEl = document.getElementById('settingTelegramChatId');
        if (tgChatEl) tgChatEl.value = data.telegram_chat_id || '';

        const gpmEl = document.getElementById('settingGpmUrl');
        if (gpmEl) gpmEl.value = data.gpm_api_base_url || '';

        // Render key pool status table
        renderKeyPoolTable(data.youtube_key_pool || []);
    } catch (err) {
        console.error('loadApiKeySettings error:', err);
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
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Lưu...';
    const resultEl = document.getElementById('saveKeysResult');
    if (resultEl) resultEl.innerHTML = '';

    const ytRaw = (document.getElementById('settingYoutubeKeys')?.value || '');
    // Normalize: join lines as comma-separated
    const ytKeys = ytRaw.split(/[\n,;]+/).map(k => k.trim()).filter(Boolean).join(',');

    const payload = {
        youtube_api_keys: ytKeys,
        gemini_api_key: document.getElementById('settingGeminiKey')?.value || '',
        openai_api_key: document.getElementById('settingOpenAiKey')?.value || '',
        telegram_bot_token: document.getElementById('settingTelegramToken')?.value || '',
        telegram_chat_id: document.getElementById('settingTelegramChatId')?.value || '',
        gpm_api_base_url: document.getElementById('settingGpmUrl')?.value || '',
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
            if (resultEl) resultEl.innerHTML = `<span style="color:#34d399;"><i class="fa-solid fa-circle-check"></i> Đã lưu toàn bộ cài đặt! Pool: ${data.pool_size} key</span>`;
            showToast(`✅ Đã lưu cấu hình & cài đặt tự động quét thành công!`, 'success');
            await loadApiKeySettings(); // refresh pool status
            loadPipelineStatus();
        } else {
            if (resultEl) resultEl.innerHTML = `<span style="color:#f87171;"><i class="fa-solid fa-circle-xmark"></i> ${escapeHtml(data.message || 'Lỗi không xác định')}</span>`;
        }
    } catch (err) {
        if (resultEl) resultEl.innerHTML = `<span style="color:#f87171;"><i class="fa-solid fa-circle-xmark"></i> Lỗi kết nối: ${err.message}</span>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = original;
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
        const mAutoDl = document.getElementById('modalAutoDownloadToggle');
        if (mAutoDl) mAutoDl.checked = autoDl;
        const mAutoRd = document.getElementById('modalAutoRenderToggle');
        if (mAutoRd) mAutoRd.checked = autoRd;

        // Populate Settings Tab Fields
        const sInterval = document.getElementById('settingSchedulerInterval');
        if (sInterval) sInterval.value = interval;
        const sUpload = document.getElementById('settingUploadInterval');
        if (sUpload) sUpload.value = uploadSec;
        const sMax = document.getElementById('settingMaxVideosPerScan');
        if (sMax) sMax.value = maxVids;
        const sDelay = document.getElementById('settingChannelDelay');
        if (sDelay) sDelay.value = delaySec;
        const sAutoDl = document.getElementById('settingAutoDownloadToggle');
        if (sAutoDl) sAutoDl.checked = autoDl;
        const sAutoRd = document.getElementById('settingAutoRenderToggle');
        if (sAutoRd) sAutoRd.checked = autoRd;
    } catch (err) {
        console.error('loadSchedulerSettings error:', err);
    }
}

async function saveSchedulerSettings(btn, fromModal = true) {
    const original = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Lưu...';
    }

    let interval, uploadSec, maxVids, delaySec, autoDl, autoRd;
    if (fromModal) {
        interval = parseInt(document.getElementById('modalSchedulerInterval')?.value) || 15;
        uploadSec = parseInt(document.getElementById('modalUploadInterval')?.value) || 60;
        maxVids = parseInt(document.getElementById('modalMaxVideosPerScan')?.value) || 5;
        delaySec = parseInt(document.getElementById('modalChannelDelay')?.value) || 2;
        autoDl = document.getElementById('modalAutoDownloadToggle')?.checked ?? true;
        autoRd = document.getElementById('modalAutoRenderToggle')?.checked ?? true;
    } else {
        interval = parseInt(document.getElementById('settingSchedulerInterval')?.value) || 15;
        uploadSec = parseInt(document.getElementById('settingUploadInterval')?.value) || 60;
        maxVids = parseInt(document.getElementById('settingMaxVideosPerScan')?.value) || 5;
        delaySec = parseInt(document.getElementById('settingChannelDelay')?.value) || 2;
        autoDl = document.getElementById('settingAutoDownloadToggle')?.checked ?? true;
        autoRd = document.getElementById('settingAutoRenderToggle')?.checked ?? true;
    }

    const payload = {
        interval_minutes: Math.max(1, interval),
        upload_interval_seconds: Math.max(10, uploadSec),
        max_videos_per_scan: Math.max(1, maxVids),
        channel_delay_seconds: Math.max(0, delaySec),
        auto_download: autoDl,
        auto_render: autoRd
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
            showToast('Lỗi khi lưu cấu hình scheduler: ' + (data.message || 'Không xác định'), true);
        }
    } catch (err) {
        showToast('Lỗi kết nối: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = original;
        }
    }
}
