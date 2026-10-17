DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Telegram Stremio V2 - Control Center</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    [x-cloak] { display: none !important; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen font-sans antialiased" x-data="dashboardApp()" x-init="initDashboard()">

  <!-- Top Navbar -->
  <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
          <i class="fa-solid fa-bolt text-white text-lg"></i>
        </div>
        <div>
          <span class="text-lg font-bold tracking-tight bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">Telegram Stremio V2</span>
          <span class="ml-2 px-2 py-0.5 text-xs rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800">Turbo Mode</span>
        </div>
      </div>

      <!-- Navigation Tabs -->
      <nav class="flex space-x-1 sm:space-x-2">
        <button @click="activeTab = 'unmatched'" :class="activeTab === 'unmatched' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'" class="px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-1.5">
          <i class="fa-solid fa-list-check"></i>
          <span>Queue</span>
          <span x-show="stats.unmatched > 0" x-text="stats.unmatched" class="px-1.5 py-0.2 rounded-full text-xs bg-rose-500 text-white font-bold"></span>
        </button>

        <button @click="activeTab = 'bots'" :class="activeTab === 'bots' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'" class="px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-1.5">
          <i class="fa-solid fa-robot"></i>
          <span>Bots & Keys</span>
          <span x-text="bots.length" class="px-1.5 py-0.2 rounded-full text-xs bg-cyan-900 text-cyan-300 font-bold"></span>
        </button>

        <button @click="activeTab = 'reindex'" :class="activeTab === 'reindex' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'" class="px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-1.5">
          <i class="fa-solid fa-arrows-rotate" :class="reindex.status === 'running' ? 'animate-spin text-cyan-400' : ''"></i>
          <span>Re-Index</span>
        </button>

        <button @click="activeTab = 'tokens'" :class="activeTab === 'tokens' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'" class="px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-1.5">
          <i class="fa-solid fa-key"></i>
          <span>Stremio</span>
        </button>

        <button @click="activeTab = 'stats'" :class="activeTab === 'stats' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'" class="px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-1.5">
          <i class="fa-solid fa-chart-simple"></i>
          <span>Stats</span>
        </button>
      </nav>
    </div>
  </header>

  <!-- Main Content -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

    <!-- TAB 1: UNMATCHED QUEUE (1-CLICK MATCHER) -->
    <section x-show="activeTab === 'unmatched'" x-cloak>
      <div class="mb-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 class="text-2xl font-bold tracking-tight">1-Click Unmatched Media Queue</h2>
          <p class="text-slate-400 text-sm mt-1">Review items skipped during indexing. Search TMDB and match with zero copy-pasting of Telegram links.</p>
        </div>
        <button @click="fetchUnmatched()" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm flex items-center gap-2 transition">
          <i class="fa-solid fa-arrow-rotate-right"></i> Refresh Queue
        </button>
      </div>

      <!-- Empty State -->
      <div x-show="unmatchedItems.length === 0" class="p-12 text-center rounded-2xl border border-slate-800 bg-slate-900/50">
        <div class="w-16 h-16 rounded-full bg-emerald-500/10 text-emerald-400 flex items-center justify-center mx-auto mb-4">
          <i class="fa-solid fa-circle-check text-2xl"></i>
        </div>
        <h3 class="text-lg font-semibold">Queue is clear!</h3>
        <p class="text-slate-400 text-sm mt-1">All channel media items have been successfully resolved and indexed.</p>
      </div>

      <!-- Unmatched Items List -->
      <div class="space-y-4">
        <template x-for="item in unmatchedItems" :key="item.id">
          <div class="p-5 rounded-xl border border-slate-800 bg-slate-900/70 hover:border-slate-700 transition" x-data="{ searchQuery: item.parsed_title || item.filename, mediaType: 'movie', season: null, episode: null, searchResults: [], isSearching: false }">
            <div class="flex flex-col md:flex-row justify-between gap-4">
              <!-- Item Details -->
              <div class="flex-1">
                <div class="flex items-center gap-2">
                  <span class="px-2 py-0.5 rounded text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20" x-text="item.quality || 'HD'"></span>
                  <span class="text-xs text-slate-500" x-text="'Chat: ' + item.chat_id + ' • Msg: ' + item.message_id"></span>
                  <span class="text-xs text-slate-500" x-text="formatBytes(item.file_size)"></span>
                </div>
                <h4 class="text-base font-semibold mt-1 text-slate-100" x-text="item.filename"></h4>
                <p x-show="item.caption" class="text-xs text-slate-400 mt-1 line-clamp-2" x-text="item.caption"></p>
              </div>

              <!-- Search Bar & Controls -->
              <div class="w-full md:w-96 flex flex-col gap-2">
                <div class="flex gap-2">
                  <input type="text" x-model="searchQuery" @keydown.enter="searchTmdb(searchQuery, mediaType, (res) => searchResults = res)" placeholder="Search TMDB title..." class="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-cyan-500">
                  <select x-model="mediaType" class="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-300 focus:outline-none">
                    <option value="movie">Movie</option>
                    <option value="tv">TV / Anime</option>
                  </select>
                  <button @click="searchTmdb(searchQuery, mediaType, (res) => searchResults = res)" class="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium transition">
                    <i class="fa-solid fa-magnifying-glass"></i>
                  </button>
                </div>

                <!-- TV season/episode inputs -->
                <div x-show="mediaType === 'tv'" class="flex gap-2 text-xs">
                  <input type="number" x-model.number="season" placeholder="Season (e.g. 1)" class="w-1/2 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-slate-100">
                  <input type="number" x-model.number="episode" placeholder="Episode (e.g. 1080)" class="w-1/2 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-slate-100">
                </div>
              </div>
            </div>

            <!-- Live Search Results Dropdown / Grid -->
            <div x-show="searchResults.length > 0" class="mt-4 pt-4 border-t border-slate-800 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              <template x-for="res in searchResults" :key="res.id">
                <div class="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 flex gap-3 items-center hover:border-cyan-500/50 transition">
                  <img :src="res.poster || 'https://via.placeholder.com/60x90?text=No+Poster'" class="w-12 h-16 object-cover rounded bg-slate-800 flex-shrink-0">
                  <div class="flex-1 min-w-0">
                    <div class="text-xs font-semibold text-slate-100 truncate" x-text="res.title"></div>
                    <div class="text-xs text-slate-400" x-text="res.year || 'Unknown Year'"></div>
                    <button @click="matchItem(item.id, res.id, res.title, res.year, mediaType, season, episode)" class="mt-1.5 px-2.5 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium flex items-center gap-1 transition">
                      <i class="fa-solid fa-check"></i> Match & Index
                    </button>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </template>
      </div>
    </section>

    <!-- TAB 2: BOTS POOL & SETTINGS -->
    <section x-show="activeTab === 'bots'" x-cloak>
      <div class="mb-6">
        <h2 class="text-2xl font-bold tracking-tight">Bot Pool & Live Configuration</h2>
        <p class="text-slate-400 text-sm mt-1">Add or remove Telegram bot workers on-the-fly without restarting the server. Manage your TMDB, TVDB, and channel keys.</p>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Bot Pool Manager -->
        <div class="p-6 rounded-2xl border border-slate-800 bg-slate-900/60">
          <h3 class="text-base font-semibold mb-3 flex items-center justify-between">
            <span class="flex items-center gap-2"><i class="fa-solid fa-robot text-cyan-400"></i> Active Telegram Streaming Bots</span>
            <span class="text-xs font-bold px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800" x-text="bots.length + ' Active'"></span>
          </h3>
          <p class="text-xs text-slate-400 mb-4">Chunks are striped across all active bots in parallel for instant (<300ms) startup.</p>

          <!-- Add Bot Input -->
          <div class="flex gap-2 mb-6">
            <input type="text" x-model="newBotToken" placeholder="Paste Bot Token (from @BotFather)..." class="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-cyan-500">
            <button @click="addBot()" class="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold transition flex items-center gap-1.5">
              <i class="fa-solid fa-plus"></i> Add Bot (Live)
            </button>
          </div>

          <!-- Bot List -->
          <div class="space-y-3">
            <template x-for="bot in bots" :key="bot.token">
              <div class="p-3.5 rounded-xl border border-slate-800 bg-slate-950/80 flex items-center justify-between gap-3">
                <div class="flex items-center gap-3">
                  <div class="w-8 h-8 rounded-lg bg-cyan-500/10 text-cyan-400 flex items-center justify-center font-bold text-xs" x-text="'#' + (bot.index + 1)"></div>
                  <div>
                    <div class="text-xs font-mono text-slate-200" x-text="bot.masked"></div>
                    <div class="text-[10px] text-emerald-400 flex items-center gap-1 mt-0.5">
                      <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Connected & Pre-warmed
                    </div>
                  </div>
                </div>

                <button @click="removeBot(bot.token)" class="px-2.5 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs font-medium transition flex items-center gap-1">
                  <i class="fa-solid fa-trash-can"></i> Remove
                </button>
              </div>
            </template>

            <div x-show="bots.length === 0" class="p-6 text-center rounded-xl border border-dashed border-slate-800 text-slate-500 text-xs">
              No bots currently active. Paste a bot token above to enable multi-bot streaming!
            </div>
          </div>
        </div>

        <!-- System Keys & Channels Settings -->
        <div class="p-6 rounded-2xl border border-slate-800 bg-slate-900/60">
          <h3 class="text-base font-semibold mb-3 flex items-center gap-2">
            <i class="fa-solid fa-sliders text-cyan-400"></i> API Keys & Monitored Channels
          </h3>
          <p class="text-xs text-slate-400 mb-4">Update metadata provider keys and Telegram channels dynamically.</p>

          <div class="space-y-4">
            <div>
              <label class="block text-xs text-slate-300 font-medium mb-1">TMDB API Key (TheMovieDatabase)</label>
              <input type="text" x-model="settingsData.tmdb_api_key" placeholder="Enter TMDB API Key..." class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-sm text-slate-100 focus:outline-none focus:border-cyan-500">
            </div>

            <div>
              <label class="block text-xs text-slate-300 font-medium mb-1">TheTVDB v4 API Key (Optional, TV & Anime)</label>
              <input type="text" x-model="settingsData.tvdb_api_key" placeholder="Enter TheTVDB API Key..." class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-sm text-slate-100 focus:outline-none focus:border-cyan-500">
            </div>

            <div>
              <label class="block text-xs text-slate-300 font-medium mb-1">Telegram Channels (Comma-separated Chat IDs or @handles)</label>
              <input type="text" x-model="channelsInput" placeholder="-1001234567890, @my_channel" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-sm text-slate-100 focus:outline-none focus:border-cyan-500">
            </div>

            <div>
              <label class="block text-xs text-slate-300 font-medium mb-1">Public Server Base URL</label>
              <input type="text" x-model="settingsData.base_url" placeholder="http://my-vps-ip:8000" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-sm text-slate-100 focus:outline-none focus:border-cyan-500">
            </div>

            <button @click="saveSettings()" class="w-full py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white text-sm font-semibold transition flex items-center justify-center gap-2 shadow-lg shadow-cyan-500/20">
              <i class="fa-solid fa-floppy-disk"></i> Save Settings
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- TAB 3: CHANNEL RE-INDEX MANAGER -->
    <section x-show="activeTab === 'reindex'" x-cloak>
      <div class="mb-6">
        <h2 class="text-2xl font-bold tracking-tight">Channel Bulk Re-Index Manager</h2>
        <p class="text-slate-400 text-sm mt-1">Re-index Telegram media channels with live telemetry, progress monitoring, and flood protection.</p>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Re-index Trigger Card -->
        <div class="lg:col-span-1 p-6 rounded-2xl border border-slate-800 bg-slate-900/60 flex flex-col justify-between">
          <div>
            <h3 class="text-base font-semibold mb-3 flex items-center gap-2">
              <i class="fa-solid fa-satellite-dish text-cyan-400"></i> Start Crawl
            </h3>
            <label class="block text-xs text-slate-400 mb-1">Telegram Channels (comma-separated chat IDs / usernames)</label>
            <input type="text" x-model="reindexChannels" placeholder="-1001234567890, @my_channel" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-sm text-slate-100 focus:outline-none focus:border-cyan-500">
            <p class="text-xs text-slate-500 mt-2">Leave blank to re-index all channels configured in your server settings.</p>
          </div>

          <button @click="triggerReindex()" :disabled="reindex.status === 'running'" class="mt-6 w-full py-3 rounded-xl font-semibold text-sm transition flex items-center justify-center gap-2" :class="reindex.status === 'running' ? 'bg-slate-800 text-slate-500 cursor-not-allowed' : 'bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/20'">
            <i class="fa-solid fa-bolt"></i>
            <span x-text="reindex.status === 'running' ? 'Re-Index in Progress...' : 'Launch Full Re-Index'"></span>
          </button>
        </div>

        <!-- Telemetry & Live Progress Card -->
        <div class="lg:col-span-2 p-6 rounded-2xl border border-slate-800 bg-slate-900/60">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-base font-semibold flex items-center gap-2">
              <i class="fa-solid fa-gauge text-cyan-400"></i> Live Telemetry
            </h3>
            <span class="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider" :class="{
              'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20': reindex.status === 'completed',
              'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 animate-pulse': reindex.status === 'running',
              'bg-slate-800 text-slate-400': reindex.status === 'idle',
              'bg-rose-500/10 text-rose-400 border border-rose-500/20': reindex.status === 'error',
            }" x-text="reindex.status"></span>
          </div>

          <div class="grid grid-cols-3 gap-4 mb-6">
            <div class="p-4 rounded-xl bg-slate-950/70 border border-slate-800/80">
              <div class="text-xs text-slate-400">Scanned Messages</div>
              <div class="text-2xl font-bold text-slate-100 mt-1" x-text="reindex.scanned || 0"></div>
            </div>
            <div class="p-4 rounded-xl bg-slate-950/70 border border-slate-800/80">
              <div class="text-xs text-slate-400">Auto-Matched</div>
              <div class="text-2xl font-bold text-emerald-400 mt-1" x-text="reindex.matched || 0"></div>
            </div>
            <div class="p-4 rounded-xl bg-slate-950/70 border border-slate-800/80">
              <div class="text-xs text-slate-400">Unmatched / Queued</div>
              <div class="text-2xl font-bold text-amber-400 mt-1" x-text="reindex.unmatched || 0"></div>
            </div>
          </div>

          <div x-show="reindex.current_channel" class="text-xs text-slate-400 mb-2">
            Scanning Channel: <span class="text-cyan-400 font-mono" x-text="reindex.current_channel"></span>
          </div>

          <!-- Animated Progress Bar -->
          <div class="w-full bg-slate-950 rounded-full h-3 overflow-hidden border border-slate-800">
            <div class="bg-gradient-to-r from-cyan-500 to-blue-500 h-3 rounded-full transition-all duration-300" :style="'width: ' + (reindex.status === 'running' ? '100%' : (reindex.status === 'completed' ? '100%' : '0%'))" :class="reindex.status === 'running' ? 'animate-pulse' : ''"></div>
          </div>
        </div>
      </div>
    </section>

    <!-- TAB 4: STREMIO TOKENS & ADDON SETUP -->
    <section x-show="activeTab === 'tokens'" x-cloak>
      <div class="mb-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 class="text-2xl font-bold tracking-tight">Stremio Addon Tokens</h2>
          <p class="text-slate-400 text-sm mt-1">Generate secure Stremio tokens for personal devices or users with 1-click install links.</p>
        </div>
        <div class="flex gap-2">
          <input type="text" x-model="newTokenName" placeholder="Device / User Name (e.g. Living Room TV)" class="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-cyan-500">
          <button @click="createToken()" class="px-4 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold transition flex items-center gap-2">
            <i class="fa-solid fa-plus"></i> Create Token
          </button>
        </div>
      </div>

      <div class="space-y-3">
        <template x-for="tok in tokens" :key="tok.token">
          <div class="p-4 rounded-xl border border-slate-800 bg-slate-900/60 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div>
              <div class="flex items-center gap-2">
                <span class="text-base font-semibold text-slate-100" x-text="tok.name"></span>
                <span class="text-xs px-2 py-0.5 rounded bg-slate-800 font-mono text-cyan-400" x-text="tok.token"></span>
              </div>
              <div class="text-xs text-slate-400 font-mono mt-1 break-all" x-text="tok.manifest_url"></div>
            </div>

            <div class="flex items-center gap-2 flex-shrink-0">
              <button @click="copyToClipboard(tok.manifest_url)" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition flex items-center gap-1.5">
                <i class="fa-solid fa-copy"></i> Copy Manifest URL
              </button>
              <a :href="tok.stremio_install_url" target="_blank" class="px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-semibold transition flex items-center gap-1.5 shadow-md shadow-purple-600/20">
                <i class="fa-solid fa-play"></i> Install to Stremio
              </a>
            </div>
          </div>
        </template>
      </div>
    </section>

    <!-- TAB 5: SYSTEM STATS & OVERVIEW -->
    <section x-show="activeTab === 'stats'" x-cloak>
      <div class="mb-6">
        <h2 class="text-2xl font-bold tracking-tight">System Performance & Library Stats</h2>
        <p class="text-slate-400 text-sm mt-1">Real-time metrics on indexed media titles, active bots, and streaming performance.</p>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <div class="p-5 rounded-2xl border border-slate-800 bg-slate-900/60">
          <div class="text-xs text-slate-400 font-medium">Total Media Records</div>
          <div class="text-3xl font-extrabold text-slate-100 mt-2" x-text="stats.total_media || 0"></div>
        </div>
        <div class="p-5 rounded-2xl border border-slate-800 bg-slate-900/60">
          <div class="text-xs text-slate-400 font-medium">Movies in Library</div>
          <div class="text-3xl font-extrabold text-cyan-400 mt-2" x-text="stats.movies || 0"></div>
        </div>
        <div class="p-5 rounded-2xl border border-slate-800 bg-slate-900/60">
          <div class="text-xs text-slate-400 font-medium">Series & Anime Episodes</div>
          <div class="text-3xl font-extrabold text-purple-400 mt-2" x-text="stats.series || 0"></div>
        </div>
        <div class="p-5 rounded-2xl border border-slate-800 bg-slate-900/60">
          <div class="text-xs text-slate-400 font-medium">Active Stremio Tokens</div>
          <div class="text-3xl font-extrabold text-emerald-400 mt-2" x-text="stats.tokens_count || 0"></div>
        </div>
      </div>
    </section>
  </main>

  <!-- Notification Toast -->
  <div x-show="toast.show" x-cloak class="fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 text-slate-100 shadow-2xl flex items-center gap-3">
    <i class="fa-solid fa-circle-check text-emerald-400 text-lg"></i>
    <span class="text-sm font-medium" x-text="toast.message"></span>
  </div>

  <script>
    function dashboardApp() {
      return {
        activeTab: 'unmatched',
        unmatchedItems: [],
        bots: [],
        newBotToken: '',
        settingsData: { tmdb_api_key: '', tvdb_api_key: '', channels: [], base_url: '' },
        channelsInput: '',
        tokens: [],
        newTokenName: '',
        reindexChannels: '',
        reindex: { status: 'idle', scanned: 0, matched: 0, unmatched: 0, current_channel: '' },
        stats: { total_media: 0, movies: 0, series: 0, unmatched: 0, tokens_count: 0 },
        toast: { show: false, message: '' },

        showToast(msg) {
          this.toast.message = msg;
          this.toast.show = true;
          setTimeout(() => this.toast.show = false, 3000);
        },

        copyToClipboard(text) {
          navigator.clipboard.writeText(text);
          this.showToast('Copied to clipboard!');
        },

        formatBytes(bytes) {
          if (!bytes || bytes === 0) return '0 B';
          const k = 1024;
          const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
          const i = Math.floor(Math.log(bytes) / Math.log(k));
          return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },

        async initDashboard() {
          await this.fetchStats();
          await this.fetchUnmatched();
          await this.fetchBots();
          await this.fetchSettings();
          await this.fetchTokens();
          this.pollReindexStatus();
        },

        async fetchStats() {
          try {
            const res = await fetch('/admin/api/stats');
            if (res.ok) this.stats = await res.json();
          } catch (e) { console.error(e); }
        },

        async fetchUnmatched() {
          try {
            const res = await fetch('/admin/api/unmatched');
            if (res.ok) {
              const data = await res.json();
              this.unmatchedItems = data.items || [];
            }
          } catch (e) { console.error(e); }
        },

        async fetchBots() {
          try {
            const res = await fetch('/admin/api/bots');
            if (res.ok) {
              const data = await res.json();
              this.bots = data.bots || [];
            }
          } catch (e) { console.error(e); }
        },

        async addBot() {
          if (!this.newBotToken) return;
          try {
            const res = await fetch('/admin/api/bots', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ token: this.newBotToken.trim() })
            });
            if (res.ok) {
              this.newBotToken = '';
              await this.fetchBots();
              this.showToast('Bot connected & added to live streaming pool!');
            } else {
              this.showToast('Failed to connect bot. Check token.');
            }
          } catch (e) { console.error(e); }
        },

        async removeBot(token) {
          if (!confirm('Remove this bot from the streaming pool?')) return;
          try {
            const res = await fetch('/admin/api/bots/remove', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ token: token })
            });
            if (res.ok) {
              await this.fetchBots();
              this.showToast('Bot stopped and removed!');
            }
          } catch (e) { console.error(e); }
        },

        async fetchSettings() {
          try {
            const res = await fetch('/admin/api/settings');
            if (res.ok) {
              const data = await res.json();
              this.settingsData = data;
              this.channelsInput = (data.channels || []).join(', ');
            }
          } catch (e) { console.error(e); }
        },

        async saveSettings() {
          const channels = this.channelsInput
            ? this.channelsInput.split(',').map(s => s.trim()).filter(Boolean)
            : [];
          try {
            const res = await fetch('/admin/api/settings', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                tmdb_api_key: this.settingsData.tmdb_api_key,
                tvdb_api_key: this.settingsData.tvdb_api_key,
                channels: channels,
                base_url: this.settingsData.base_url
              })
            });
            if (res.ok) {
              await this.fetchSettings();
              this.showToast('Settings saved successfully!');
            }
          } catch (e) { console.error(e); }
        },

        async fetchTokens() {
          try {
            const res = await fetch('/admin/api/tokens');
            if (res.ok) {
              const data = await res.json();
              this.tokens = data.tokens || [];
            }
          } catch (e) { console.error(e); }
        },

        async createToken() {
          try {
            const res = await fetch('/admin/api/tokens', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: this.newTokenName || 'User' })
            });
            if (res.ok) {
              this.newTokenName = '';
              await this.fetchTokens();
              await this.fetchStats();
              this.showToast('Created Stremio token!');
            }
          } catch (e) { console.error(e); }
        },

        async searchTmdb(query, type, cb) {
          if (!query) return;
          try {
            const res = await fetch(`/admin/api/search-tmdb?query=${encodeURIComponent(query)}&type=${type}`);
            if (res.ok) {
              const data = await res.json();
              cb(data.results || []);
            }
          } catch (e) { console.error(e); }
        },

        async matchItem(unmatchedId, tmdbId, title, year, mediaType, season, episode) {
          try {
            const res = await fetch('/admin/api/match', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                unmatched_id: unmatchedId,
                tmdb_id: tmdbId,
                canonical_title: title,
                year: year,
                media_type: mediaType,
                season: season,
                episode: episode
              })
            });
            if (res.ok) {
              this.unmatchedItems = this.unmatchedItems.filter(i => i.id !== unmatchedId);
              await this.fetchStats();
              this.showToast(`Matched "${title}"!`);
            }
          } catch (e) { console.error(e); }
        },

        async triggerReindex() {
          const channels = this.reindexChannels
            ? this.reindexChannels.split(',').map(s => s.trim()).filter(Boolean)
            : null;
          try {
            const res = await fetch('/admin/api/reindex', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ channels: channels })
            });
            if (res.ok) {
              this.showToast('Started re-indexing channels!');
            }
          } catch (e) { console.error(e); }
        },

        pollReindexStatus() {
          setInterval(async () => {
            try {
              const res = await fetch('/admin/api/reindex/status');
              if (res.ok) {
                this.reindex = await res.json();
              }
            } catch (e) {}
          }, 2000);
        }
      }
    }
  </script>
</body>
</html>
"""
