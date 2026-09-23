document.addEventListener('DOMContentLoaded', () => {
    // Tab switching
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            tabButtons.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            btn.classList.add('active');
            const target = btn.dataset.tab;
            document.getElementById(target).classList.add('active');

            if (target === 'tab-gallery') {
                loadGallery();
            }
        });
    });

    // File Selection & Drag-and-Drop
    const dropzone = document.getElementById('dropzone');
    const videoInput = document.getElementById('video-input');
    const selectedFileInfo = document.getElementById('selected-file-info');
    const selectedFileName = document.getElementById('selected-file-name');
    const selectedFileSize = document.getElementById('selected-file-size');
    const btnProcess = document.getElementById('btn-process');
    const saveAnnotatedCheckbox = document.getElementById('save-annotated');

    let selectedFile = null;

    dropzone.addEventListener('click', () => videoInput.click());

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
        });
    });

    dropzone.addEventListener('drop', (e) => {
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    videoInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    function handleFileSelect(file) {
        if (!file.type.startsWith('video/') && !file.name.match(/\.(mp4|avi|mov|mkv|webm)$/i)) {
            alert('Please select a valid video file (.mp4, .avi, .mov, .mkv, .webm).');
            return;
        }
        selectedFile = file;
        selectedFileName.textContent = file.name;
        selectedFileSize.textContent = formatBytes(file.size);
        selectedFileInfo.style.display = 'flex';
        btnProcess.disabled = false;
        btnProcess.textContent = `🚀 Process ${file.name}`;
    }

    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    // Process Video Submission
    const progressCard = document.getElementById('progress-card');
    const progressBarFill = document.getElementById('progress-bar-fill');
    const progressText = document.getElementById('progress-text');
    const progressPercent = document.getElementById('progress-percent');
    const liveStatFrames = document.getElementById('live-stat-frames');
    const liveStatTime = document.getElementById('live-stat-time');
    const liveStatFps = document.getElementById('live-stat-fps');
    const liveStatDetected = document.getElementById('live-stat-detected');
    const livePillMatches = document.getElementById('live-pill-matches');
    const liveStatMatches = document.getElementById('live-stat-matches');
    const resultsCard = document.getElementById('results-card');

    let pollInterval = null;

    btnProcess.addEventListener('click', async () => {
        if (!selectedFile) return;

        btnProcess.disabled = true;
        progressCard.style.display = 'block';
        resultsCard.style.display = 'none';
        progressBarFill.style.width = '5%';
        progressPercent.textContent = '0%';
        progressText.textContent = `Uploading ${selectedFile.name}...`;

        liveStatFrames.textContent = '0 / 0';
        liveStatTime.textContent = '00:00';
        liveStatFps.textContent = '0.0 fps';
        liveStatDetected.textContent = '0';
        livePillMatches.style.display = 'none';

        const formData = new FormData();
        formData.append('video', selectedFile);
        formData.append('save_annotated', saveAnnotatedCheckbox.checked);

        try {
            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/api/process_video', true);

            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const uploadPct = Math.round((e.loaded / e.total) * 100);
                    if (uploadPct < 100) {
                        progressBarFill.style.width = `${Math.min(25, uploadPct * 0.25)}%`;
                        progressText.textContent = `Uploading video: ${uploadPct}%`;
                    } else {
                        progressText.textContent = 'Initializing frame extraction & AI face recognition...';
                    }
                }
            };

            xhr.onload = () => {
                if (xhr.status === 200) {
                    const resp = JSON.parse(xhr.responseText);
                    const jobId = resp.job_id;
                    startProgressPolling(jobId);
                } else {
                    let errMsg = 'Upload failed';
                    try { errMsg = JSON.parse(xhr.responseText).error || errMsg; } catch(e) {}
                    alert(`Error: ${errMsg}`);
                    progressCard.style.display = 'none';
                    btnProcess.disabled = false;
                }
            };

            xhr.onerror = () => {
                alert('A network error occurred while uploading.');
                progressCard.style.display = 'none';
                btnProcess.disabled = false;
            };

            xhr.send(formData);

        } catch (err) {
            console.error(err);
            alert(`Error: ${err.message}`);
            progressCard.style.display = 'none';
            btnProcess.disabled = false;
        }
    });

    function startProgressPolling(jobId) {
        if (pollInterval) clearInterval(pollInterval);

        pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`/api/progress/${jobId}`);
                if (!res.ok) return;

                const job = await res.json();

                if (job.status === 'processing') {
                    const pct = job.percent || 0;
                    progressBarFill.style.width = `${pct}%`;
                    progressPercent.textContent = `${pct}%`;
                    progressText.textContent = `Processing Video • Frame ${job.current_frame} / ${job.total_frames}`;

                    liveStatFrames.textContent = `${job.current_frame} / ${job.total_frames}`;
                    liveStatTime.textContent = job.current_time || '00:00';
                    liveStatFps.textContent = `${job.proc_fps || 0} fps`;
                    liveStatDetected.textContent = job.detected_count || 0;

                    if (job.match_count && job.match_count > 0) {
                        livePillMatches.style.display = 'inline-flex';
                        liveStatMatches.textContent = `🎯 ${job.match_count} Cross-Video Match${job.match_count > 1 ? 'es' : ''}`;
                    }
                } else if (job.status === 'completed') {
                    clearInterval(pollInterval);
                    pollInterval = null;

                    progressBarFill.style.width = '100%';
                    progressPercent.textContent = '100%';
                    progressText.textContent = 'Processing Complete!';

                    setTimeout(() => {
                        progressCard.style.display = 'none';
                        renderResults(job.result);
                        btnProcess.disabled = false;
                    }, 500);
                } else if (job.status === 'error') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    alert(`Error processing video: ${job.error}`);
                    progressCard.style.display = 'none';
                    btnProcess.disabled = false;
                }
            } catch (e) {
                console.error('Polling error:', e);
            }
        }, 250);
    }

    function renderResults(data) {
        resultsCard.style.display = 'block';

        document.getElementById('res-total-faces').textContent = data.detected_people.length;
        document.getElementById('res-new-identities').textContent = data.new_identities_count;
        document.getElementById('res-cross-matches').textContent = data.cross_matches_count;
        document.getElementById('res-gallery-total').textContent = data.gallery_total_people;

        const downloadActions = document.getElementById('download-actions');
        downloadActions.innerHTML = '';

        if (data.annotated_video_url) {
            const btnVideo = document.createElement('a');
            btnVideo.href = data.annotated_video_url;
            btnVideo.className = 'btn-action primary';
            btnVideo.innerHTML = '📥 Download Annotated Video';
            downloadActions.appendChild(btnVideo);
        }

        const btnExcel = document.createElement('a');
        btnExcel.href = data.report_url;
        btnExcel.className = 'btn-action';
        btnExcel.innerHTML = '📊 Download Cross-Video Report (Excel)';
        downloadActions.appendChild(btnExcel);

        // Render detected people cards
        const grid = document.getElementById('detected-people-grid');
        grid.innerHTML = '';

        if (data.detected_people.length === 0) {
            grid.innerHTML = '<p style="color: var(--text-secondary); grid-column: 1/-1;">No faces detected in this video.</p>';
            return;
        }

        data.detected_people.forEach(person => {
            const card = document.createElement('div');
            card.className = `person-card ${person.matched_from ? 'matched' : ''}`;

            const badgeHtml = person.matched_from
                ? `<span class="badge badge-match">🎯 Matched from ${person.matched_from}</span>`
                : (person.is_new ? `<span class="badge badge-new">✨ New ID</span>` : `<span class="badge badge-single">Seen</span>`);

            const tagsHtml = person.timestamps.map(t => `<span class="time-tag">${t}</span>`).join('');

            card.innerHTML = `
                <div class="person-img-wrap">
                    <img class="person-img" src="${person.thumbnail_url}" onerror="this.onerror=null; this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>👤</text></svg>';" alt="${person.id}">
                </div>
                <div class="person-info">
                    <div class="person-header">
                        <span class="person-id">${person.id}</span>
                        ${badgeHtml}
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary);">
                        Appeared at timestamps:
                    </div>
                    <div class="timestamp-tags">
                        ${tagsHtml || '<span style="font-size:11px; color:#64748b;">No timestamp recorded</span>'}
                    </div>
                </div>
            `;
            grid.appendChild(card);
        });
    }

    // Gallery View
    const galleryGrid = document.getElementById('gallery-grid');
    const galleryCountBadge = document.getElementById('gallery-count-badge');
    const btnResetGallery = document.getElementById('btn-reset-gallery');

    async function loadGallery() {
        galleryGrid.innerHTML = '<p style="color: var(--text-secondary);">Loading gallery...</p>';
        try {
            const res = await fetch('/api/gallery');
            const data = await res.json();
            galleryCountBadge.textContent = `${data.total_count} People (${data.cross_matches_count} Cross-Matches)`;

            galleryGrid.innerHTML = '';
            if (data.people.length === 0) {
                galleryGrid.innerHTML = '<p style="color: var(--text-secondary); grid-column: 1/-1;">The gallery is currently empty. Process Video 1 to start cataloging identities!</p>';
                return;
            }

            data.people.forEach(person => {
                const card = document.createElement('div');
                card.className = `person-card ${person.is_cross_match ? 'matched' : ''}`;

                const badgeHtml = person.is_cross_match
                    ? `<span class="badge badge-match">🎯 ${person.total_videos} Videos</span>`
                    : `<span class="badge badge-single">1 Video</span>`;

                let appearancesHtml = '';
                for (const [vName, times] of Object.entries(person.video_detections)) {
                    appearancesHtml += `<div style="font-size:12px; margin-top:4px;"><strong style="color:var(--text-primary);">${vName}:</strong> <span style="color:var(--accent-blue);">${times.join(', ') || 'Detected'}</span></div>`;
                }

                card.innerHTML = `
                    <div class="person-img-wrap">
                        <img class="person-img" src="${person.thumbnail_url}" onerror="this.onerror=null; this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>👤</text></svg>';" alt="${person.id}">
                    </div>
                    <div class="person-info">
                        <div class="person-header">
                            <span class="person-id">${person.id}</span>
                            ${badgeHtml}
                        </div>
                        <div style="font-size: 11px; color: var(--text-secondary);">First Seen: ${person.first_seen_video}</div>
                        <div style="margin-top: 6px;">
                            ${appearancesHtml}
                        </div>
                    </div>
                `;
                galleryGrid.appendChild(card);
            });

        } catch (e) {
            console.error(e);
            galleryGrid.innerHTML = '<p style="color: #f87171;">Failed to load gallery.</p>';
        }
    }

    btnResetGallery.addEventListener('click', async () => {
        if (!confirm('Are you sure you want to reset the entire gallery? All discovered IDs (Person_001, etc.) will be deleted and reset.')) {
            return;
        }
        try {
            await fetch('/api/reset_gallery', { method: 'POST' });
            alert('Gallery has been reset successfully.');
            loadGallery();
        } catch (e) {
            alert('Failed to reset gallery.');
        }
    });

});
