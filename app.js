/**
 * Vacation Planner Frontend Client Logic
 * Handles API communication, pipeline visualization, markdown rendering,
 * audio playback, conversation history, and user memory.
 */

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const plannerForm = document.getElementById('planner-form');
  const travelQueryInput = document.getElementById('travel-query');
  const btnSubmit = document.getElementById('btn-submit-plan');
  const pipelineSection = document.getElementById('pipeline-progress');
  const resultsSection = document.getElementById('results-section');
  const errorBanner = document.getElementById('error-banner');
  const errorMessage = document.getElementById('error-message');
  const btnCloseError = document.getElementById('btn-close-error');

  // Filters
  const btnToggleFilters = document.getElementById('btn-toggle-filters');
  const advancedFilters = document.getElementById('advanced-filters');
  const filterDest = document.getElementById('filter-dest');
  const filterDays = document.getElementById('filter-days');
  const filterBudget = document.getElementById('filter-budget');
  const filterRating = document.getElementById('filter-rating');
  const filterSort = document.getElementById('filter-sort');

  // Stepper Elements
  const stepParser = document.getElementById('step-parser');
  const stepPlanner = document.getElementById('step-planner');
  const stepSpecialized = document.getElementById('step-specialized');
  const stepCritic = document.getElementById('step-critic');
  const stepItinerary = document.getElementById('step-itinerary');

  // Results Displays
  const planDestTitle = document.getElementById('plan-destination-title');
  const badgeBudget = document.getElementById('badge-budget');
  const badgeDuration = document.getElementById('badge-duration');
  const badgeCriticScore = document.getElementById('badge-critic-score');
  const itineraryContent = document.getElementById('itinerary-markdown-content');
  const flightsGrid = document.getElementById('flights-grid');
  const hotelsGrid = document.getElementById('hotels-grid');
  const weatherDisplay = document.getElementById('weather-display');
  const attractionsGrid = document.getElementById('attractions-grid');
  const budgetDisplay = document.getElementById('budget-display');
  const criticDisplay = document.getElementById('critic-display');

  // Counters
  const countFlights = document.getElementById('count-flights');
  const countHotels = document.getElementById('count-hotels');
  const countAttractions = document.getElementById('count-attractions');

  // Voice Player
  const btnPlayVoice = document.getElementById('btn-play-voice');
  const voiceBtnLabel = document.getElementById('voice-btn-label');
  const audioPlayer = document.getElementById('audio-player');

  // Memory & History Modals
  const btnOpenMemory = document.getElementById('btn-open-memory');
  const btnCloseMemory = document.getElementById('btn-close-memory');
  const btnCancelMemory = document.getElementById('btn-cancel-memory');
  const modalMemory = document.getElementById('modal-memory');
  const formMemory = document.getElementById('form-user-memory');

  const btnOpenHistory = document.getElementById('btn-open-history');
  const btnCloseHistory = document.getElementById('btn-close-history');
  const drawerHistory = document.getElementById('drawer-history');
  const historyList = document.getElementById('history-list');

  let currentPlanResponse = null;

  // =========================================================================
  // INITIALIZATION & QUICK CHIPS
  // =========================================================================
  checkHealth();
  loadUserMemory();

  // Quick suggestion chips
  document.querySelectorAll('.quick-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      travelQueryInput.value = chip.dataset.query;
      travelQueryInput.focus();
    });
  });

  // Toggle Advanced Filters
  btnToggleFilters.addEventListener('click', () => {
    advancedFilters.classList.toggle('hidden');
    const arrow = btnToggleFilters.querySelector('.toggle-arrow');
    if (advancedFilters.classList.contains('hidden')) {
      arrow.style.transform = 'rotate(0deg)';
    } else {
      arrow.style.transform = 'rotate(180deg)';
    }
  });

  // Tab Switching
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const target = document.getElementById(btn.dataset.tab);
      if (target) target.classList.add('active');
    });
  });

  // Print Itinerary
  document.getElementById('btn-print-itinerary').addEventListener('click', () => {
    window.print();
  });

  // Error Close
  btnCloseError.addEventListener('click', () => errorBanner.classList.add('hidden'));

  // =========================================================================
  // FORM SUBMISSION & PIPELINE EXECUTION
  // =========================================================================
  plannerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = travelQueryInput.value.trim();
    if (!query) return;

    // Reset UI & Show Stepper
    errorBanner.classList.add('hidden');
    resultsSection.classList.add('hidden');
    pipelineSection.classList.remove('hidden');
    btnSubmit.disabled = true;

    // Reset Steppers
    resetSteppers();
    setStepState(stepParser, 'active', 'Extracting constraints...');

    // Collect payload
    const payload = {
      query: query,
      user_id: 'default_user',
      explicit_destination: filterDest.value.trim() || null,
      explicit_days: filterDays.value ? parseInt(filterDays.value) : null,
      explicit_budget: filterBudget.value ? parseFloat(filterBudget.value) : null,
      sort_by: filterSort.value || 'price',
      min_rating: filterRating.value ? parseFloat(filterRating.value) : 3.5
    };

    try {
      // Simulate/Show visual step progression
      setTimeout(() => {
        setStepState(stepParser, 'completed', 'Constraints parsed');
        setStepState(stepPlanner, 'active', 'Orchestrating agents...');
      }, 500);

      setTimeout(() => {
        setStepState(stepPlanner, 'completed', 'Agents invoked');
        setStepState(stepSpecialized, 'active', 'Querying Flights, Hotels, Weather, Attractions...');
      }, 1200);

      const response = await fetch('/api/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to generate vacation plan.');
      }

      const data = await response.json();
      currentPlanResponse = data;

      // Finish Stepper
      setStepState(stepSpecialized, 'completed', 'Data retrieved');
      setStepState(stepCritic, 'completed', `Score: ${data.critic_result?.score || 100}/100`);
      setStepState(stepItinerary, 'completed', 'Plan ready!');

      setTimeout(() => {
        pipelineSection.classList.add('hidden');
        renderResults(data);
        resultsSection.classList.remove('hidden');
        resultsSection.scrollIntoView({ behavior: 'smooth' });
      }, 600);

    } catch (err) {
      console.error(err);
      pipelineSection.classList.add('hidden');
      errorMessage.textContent = err.message;
      errorBanner.classList.remove('hidden');
    } finally {
      btnSubmit.disabled = false;
    }
  });

  // =========================================================================
  // RENDER PLAN RESULTS
  // =========================================================================
  function renderResults(data) {
    const parsed = data.parsed_requirements;
    const planner = data.planner_result;
    const critic = data.critic_result;

    // Header Summary
    planDestTitle.textContent = `Vacation Plan: ${parsed.destination} (${parsed.days} Days)`;
    badgeBudget.innerHTML = `<i class="fa-solid fa-wallet"></i> Target: ₹${parsed.budget.toLocaleString()}`;
    badgeDuration.innerHTML = `<i class="fa-regular fa-calendar"></i> ${parsed.days} Days`;
    badgeCriticScore.innerHTML = `<i class="fa-solid fa-star"></i> Critic Score: ${critic?.score || 100}/100`;

    // 1. Markdown Itinerary
    if (window.marked) {
      itineraryContent.innerHTML = marked.parse(data.itinerary_markdown);
    } else {
      itineraryContent.textContent = data.itinerary_markdown;
    }

    // 2. Flights Cards
    const flights = planner.flights || [];
    countFlights.textContent = flights.length;
    if (flights.length === 0) {
      flightsGrid.innerHTML = '<p class="empty-state">No direct flights matched for this destination.</p>';
    } else {
      flightsGrid.innerHTML = flights.map(f => `
        <div class="data-card">
          <div class="card-title-row">
            <span class="card-title">${f.airline || 'Airline'}</span>
            <span class="card-badge">Flight #${f.flight_id || 'Direct'}</span>
          </div>
          <ul class="card-meta-list">
            <li><i class="fa-solid fa-plane-departure"></i> ${f.source || 'Origin'} ➔ ${f.destination}</li>
            <li><i class="fa-regular fa-clock"></i> Departure: ${f['departure time'] || f.departure_time || '08:00 AM'}</li>
            <li><i class="fa-regular fa-clock"></i> Arrival: ${f.arrival_time || '10:30 AM'}</li>
            <li><i class="fa-solid fa-hourglass-half"></i> Duration: ${f.duration || '2h 30m'}</li>
          </ul>
          <div class="card-price">₹${Number(f.price || 0).toLocaleString()} <span style="font-size:0.75rem; color:var(--text-subtle); font-weight:normal;">/ person</span></div>
        </div>
      `).join('');
    }

    // 3. Hotels Cards
    const hotels = planner.hotels || [];
    countHotels.textContent = hotels.length;
    if (hotels.length === 0) {
      hotelsGrid.innerHTML = '<p class="empty-state">No hotels matched the exact rating/budget criteria.</p>';
    } else {
      hotelsGrid.innerHTML = hotels.map(h => `
        <div class="data-card">
          <div class="card-title-row">
            <span class="card-title">${h.hotel_name}</span>
            <span class="card-badge"><i class="fa-solid fa-star" style="color:#F59E0B;"></i> ${h.rating}</span>
          </div>
          <ul class="card-meta-list">
            <li><i class="fa-solid fa-location-dot"></i> ${h.city}</li>
            <li><i class="fa-solid fa-bell-concierge"></i> ${h.facilities || 'Free Wi-Fi, AC, Breakfast'}</li>
          </ul>
          <div class="card-price">₹${Number(h.cost || 0).toLocaleString()} <span style="font-size:0.75rem; color:var(--text-subtle); font-weight:normal;">/ night</span></div>
        </div>
      `).join('');
    }

    // 4. Weather Display
    const weatherList = planner.weather || [];
    if (weatherList.length === 0) {
      weatherDisplay.innerHTML = '<p class="empty-state">No weather data found.</p>';
    } else {
      const w = weatherList[0];
      weatherDisplay.innerHTML = `
        <div class="data-card" style="max-width: 600px;">
          <div class="card-title-row">
            <span class="card-title">${w.destination} Climate Forecast</span>
            <span class="card-badge">${w.season || 'Current Season'}</span>
          </div>
          <div style="display: flex; gap: 24px; margin: 16px 0;">
            <div><span style="font-size: 2rem; font-weight:800; color:var(--primary);">${w.temperature}°C</span><br><small style="color:var(--text-subtle);">Temperature</small></div>
            <div><span style="font-size: 2rem; font-weight:800; color:var(--accent);">${w.rainfall} mm</span><br><small style="color:var(--text-subtle);">Rainfall</small></div>
            <div><span style="font-size: 2rem; font-weight:800; color:var(--success);">${w.humidity}%</span><br><small style="color:var(--text-subtle);">Humidity</small></div>
          </div>
          <p style="font-size: 0.9rem; color: var(--text-muted);"><strong>Packing Advice:</strong> Lightweight cottons, sun protection, sunglasses, and comfortable footwear.</p>
        </div>
      `;
    }

    // 5. Attractions Cards
    const attractions = planner.attractions || [];
    countAttractions.textContent = attractions.length;
    if (attractions.length === 0) {
      attractionsGrid.innerHTML = '<p class="empty-state">No attractions found.</p>';
    } else {
      attractionsGrid.innerHTML = attractions.map(a => `
        <div class="data-card">
          <div class="card-title-row">
            <span class="card-title">${a.attraction_name}</span>
            <span class="card-badge">${a.category || 'Sightseeing'}</span>
          </div>
          <ul class="card-meta-list">
            <li><i class="fa-solid fa-location-dot"></i> ${a.city || a.destination || parsed.destination}</li>
            <li><i class="fa-regular fa-clock"></i> ${a.timings || '09:00 AM - 05:00 PM'}</li>
          </ul>
          <div class="card-price">₹${Number(a.entry_fee || 0).toLocaleString()} <span style="font-size:0.75rem; color:var(--text-subtle); font-weight:normal;">entry fee</span></div>
        </div>
      `).join('');
    }

    // 6. Budget Display
    const b = planner.budget || {};
    const totalEst = Number(b.total_budget || 0);
    const targetBudget = Number(parsed.budget || 0);
    const diff = targetBudget - totalEst;
    const isUnder = diff >= 0;

    budgetDisplay.innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px;">
        <div class="data-card">
          <small style="color:var(--text-subtle);">Flight (Roundtrip)</small>
          <div style="font-size:1.3rem; font-weight:700;">₹${Number(b.flight_cost || 0).toLocaleString()}</div>
        </div>
        <div class="data-card">
          <small style="color:var(--text-subtle);">Hotel (${parsed.days} Days)</small>
          <div style="font-size:1.3rem; font-weight:700;">₹${Number(b.hotel_cost || 0).toLocaleString()}</div>
        </div>
        <div class="data-card">
          <small style="color:var(--text-subtle);">Food & Dining</small>
          <div style="font-size:1.3rem; font-weight:700;">₹${Number(b.food_cost || 0).toLocaleString()}</div>
        </div>
        <div class="data-card">
          <small style="color:var(--text-subtle);">Taxi & Transit</small>
          <div style="font-size:1.3rem; font-weight:700;">₹${Number(b.taxi_cost || 0).toLocaleString()}</div>
        </div>
        <div class="data-card">
          <small style="color:var(--text-subtle);">Attractions</small>
          <div style="font-size:1.3rem; font-weight:700;">₹${Number(b.activities || 0).toLocaleString()}</div>
        </div>
      </div>

      <div class="data-card" style="background: rgba(6, 182, 212, 0.08); border-color: var(--primary);">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px;">
          <div>
            <h3>Total Estimated Cost: ₹${totalEst.toLocaleString()}</h3>
            <p style="color:var(--text-muted); font-size:0.9rem;">Target Budget: ₹${targetBudget.toLocaleString()}</p>
          </div>
          <div>
            <span class="meta-badge ${isUnder ? 'score-badge' : ''}" style="${!isUnder ? 'background:rgba(239,68,68,0.2); color:#F87171;' : ''}">
              <i class="fa-solid ${isUnder ? 'fa-circle-check' : 'fa-circle-exclamation'}"></i>
              ${isUnder ? `Surplus: ₹${diff.toLocaleString()}` : `Over by: ₹${Math.abs(diff).toLocaleString()}`}
            </span>
          </div>
        </div>
      </div>
    `;

    // 7. Critic Display
    if (critic) {
      criticDisplay.innerHTML = `
        <div class="critic-score-hero">
          <div class="score-circle">${critic.score}%</div>
          <div>
            <h4>Quality & Constraint Rating</h4>
            <p style="color:var(--text-muted); font-size:0.9rem;">The Critic / Reflection layer verified budget math, timing alignment, and requirements.</p>
          </div>
        </div>
        <ul class="critic-checklist">
          ${(critic.checks || []).map(c => `
            <li class="critic-item ${c.passed ? 'pass' : 'fail'}">
              <i class="fa-solid ${c.passed ? 'fa-circle-check' : 'fa-triangle-exclamation'}"></i>
              <span><strong>${c.aspect}:</strong> ${c.details}</span>
            </li>
          `).join('')}
        </ul>
        ${(critic.warnings || []).length > 0 ? `
          <div style="margin-top:16px; padding:12px; background:rgba(245,158,11,0.1); border:1px solid var(--warning); border-radius:var(--radius-sm); color:#FCD34D;">
            <strong>Suggestions:</strong> ${critic.suggestions.join(' ')}
          </div>
        ` : ''}
      `;
    }
  }

  // =========================================================================
  // STEPPER HELPERS
  // =========================================================================
  function resetSteppers() {
    [stepParser, stepPlanner, stepSpecialized, stepCritic, stepItinerary].forEach(s => {
      s.classList.remove('active', 'completed');
      s.querySelector('.step-status').textContent = 'Waiting...';
    });
  }

  function setStepState(element, state, text) {
    element.classList.remove('active', 'completed');
    element.classList.add(state);
    element.querySelector('.step-status').textContent = text;
  }

  // =========================================================================
  // ELEVENLABS VOICE SYNTHESIS
  // =========================================================================
  btnPlayVoice.addEventListener('click', async () => {
    if (!currentPlanResponse) return;

    if (!audioPlayer.paused && audioPlayer.src) {
      audioPlayer.pause();
      voiceBtnLabel.textContent = 'Listen (ElevenLabs)';
      return;
    }

    voiceBtnLabel.textContent = 'Generating Voice...';
    btnPlayVoice.disabled = true;

    try {
      const response = await fetch('/api/voice/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: currentPlanResponse.itinerary_markdown.slice(0, 1500)
        })
      });

      if (!response.ok) {
        throw new Error('Failed to generate audio.');
      }

      const blob = await response.blob();
      const audioUrl = URL.createObjectURL(blob);
      audioPlayer.src = audioUrl;
      audioPlayer.play();
      voiceBtnLabel.textContent = 'Pause Narration';

      audioPlayer.onended = () => {
        voiceBtnLabel.textContent = 'Listen (ElevenLabs)';
      };

    } catch (err) {
      console.warn('ElevenLabs error, using browser speech synthesis fallback:', err);
      speakBrowserFallback(currentPlanResponse.itinerary_markdown);
      voiceBtnLabel.textContent = 'Speaking (Fallback)';
    } finally {
      btnPlayVoice.disabled = false;
    }
  });

  function speakBrowserFallback(markdown) {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    // Strip markdown formatting for cleaner speech
    const cleanText = markdown.replace(/[#*_`|>-]/g, '').slice(0, 600);
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.0;
    utterance.onend = () => { voiceBtnLabel.textContent = 'Listen (ElevenLabs)'; };
    window.speechSynthesis.speak(utterance);
  }

  // =========================================================================
  // USER MEMORY MODAL
  // =========================================================================
  btnOpenMemory.addEventListener('click', () => {
    loadUserMemory();
    modalMemory.classList.remove('hidden');
  });

  [btnCloseMemory, btnCancelMemory].forEach(btn => {
    btn.addEventListener('click', () => modalMemory.classList.add('hidden'));
  });

  async function loadUserMemory() {
    try {
      const resp = await fetch('/api/memory?user_id=default_user');
      if (resp.ok) {
        const mem = await resp.json();
        document.getElementById('mem-name').value = mem.name || '';
        document.getElementById('mem-airline').value = mem.preferred_airline || '';
        document.getElementById('mem-hotel-rating').value = mem.hotel_rating_preference || 4.0;
        document.getElementById('mem-budget').value = mem.budget_preference || '';
        document.getElementById('mem-preferences').value = (mem.travel_preferences || []).join(', ');
      }
    } catch (err) {
      console.warn('Memory load error:', err);
    }
  }

  formMemory.addEventListener('submit', async (e) => {
    e.preventDefault();
    const prefs = document.getElementById('mem-preferences').value
      .split(',')
      .map(p => p.trim())
      .filter(p => p.length > 0);

    const memData = {
      user_id: 'default_user',
      name: document.getElementById('mem-name').value.trim() || 'Traveler',
      preferred_airline: document.getElementById('mem-airline').value.trim() || null,
      hotel_rating_preference: parseFloat(document.getElementById('mem-hotel-rating').value),
      budget_preference: document.getElementById('mem-budget').value ? parseFloat(document.getElementById('mem-budget').value) : null,
      travel_preferences: prefs
    };

    try {
      await fetch('/api/memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(memData)
      });
      modalMemory.classList.add('hidden');
    } catch (err) {
      alert('Failed to save memory: ' + err.message);
    }
  });

  // =========================================================================
  // CONVERSATION HISTORY DRAWER
  // =========================================================================
  btnOpenHistory.addEventListener('click', async () => {
    drawerHistory.classList.remove('hidden');
    try {
      const resp = await fetch('/api/history?user_id=default_user');
      if (resp.ok) {
        const history = await resp.json();
        if (!history || history.length === 0) {
          historyList.innerHTML = '<p class="empty-state">No previous trips recorded yet.</p>';
          return;
        }

        historyList.innerHTML = history.map(item => `
          <div class="history-item" data-query="${item.question}">
            <h4>${item.question}</h4>
            <p><i class="fa-regular fa-clock"></i> ${new Date(item.timestamp || Date.now()).toLocaleString()}</p>
          </div>
        `).join('');

        historyList.querySelectorAll('.history-item').forEach(card => {
          card.addEventListener('click', () => {
            travelQueryInput.value = card.dataset.query;
            drawerHistory.classList.add('hidden');
            plannerForm.dispatchEvent(new Event('submit'));
          });
        });
      }
    } catch (err) {
      console.warn('History fetch error:', err);
    }
  });

  btnCloseHistory.addEventListener('click', () => drawerHistory.classList.add('hidden'));

  // =========================================================================
  // RAG TRAVEL GUIDE Q&A
  // =========================================================================
  const ragQueryInput = document.getElementById('rag-query-input');
  const btnAskRag = document.getElementById('btn-ask-rag');
  const ragAnswerContainer = document.getElementById('rag-answer-container');
  const ragAnswerText = document.getElementById('rag-answer-text');
  const ragChunksContainer = document.getElementById('rag-chunks-container');

  btnAskRag.addEventListener('click', async () => {
    const q = ragQueryInput.value.trim();
    if (!q) return;

    btnAskRag.disabled = true;
    btnAskRag.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Searching...';
    ragAnswerContainer.classList.add('hidden');
    ragChunksContainer.innerHTML = '';

    const currentDest = currentPlanResponse?.parsed_requirements?.destination || null;

    try {
      const resp = await fetch('/api/rag/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, destination: currentDest })
      });

      if (!resp.ok) throw new Error('Failed to query travel knowledge.');

      const result = await resp.json();

      // Render answer
      ragAnswerContainer.classList.remove('hidden');
      if (window.marked) {
        ragAnswerText.innerHTML = marked.parse(result.answer);
      } else {
        ragAnswerText.textContent = result.answer;
      }

      // Render retrieved chunks
      const chunks = result.retrieved_chunks || [];
      if (chunks.length > 0) {
        ragChunksContainer.innerHTML = chunks.map(c => `
          <div class="data-card">
            <div class="card-title-row">
              <span class="card-title">${c.document_name}</span>
              <span class="card-badge">${c.category}</span>
            </div>
            <p style="font-size:0.85rem; color:var(--text-muted); line-height:1.5;">${c.chunk_text}</p>
            ${c.similarity ? `<div style="margin-top:8px; font-size:0.75rem; color:var(--primary);">Similarity: ${(c.similarity * 100).toFixed(1)}%</div>` : ''}
          </div>
        `).join('');
      }
    } catch (err) {
      alert('Error searching travel knowledge: ' + err.message);
    } finally {
      btnAskRag.disabled = false;
      btnAskRag.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Ask Guide';
    }
  });

  // =========================================================================
  // SYSTEM HEALTH CHECK
  // =========================================================================
  async function checkHealth() {
    try {
      const resp = await fetch('/api/health');
      if (resp.ok) {
        const status = await resp.json();
        const indicator = document.getElementById('system-status-indicator');
        indicator.classList.remove('offline');
        indicator.classList.add('online');
        indicator.innerHTML = '<span class="dot"></span> Online';
      }
    } catch (err) {
      const indicator = document.getElementById('system-status-indicator');
      indicator.classList.remove('online');
      indicator.classList.add('offline');
      indicator.innerHTML = '<span class="dot" style="background:#EF4444;"></span> Offline';
    }
  }
});

