document.addEventListener('DOMContentLoaded', () => {
  // ==========================================================================
  // Auto-dismiss Alerts
  // ==========================================================================
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(alert => {
    const closeBtn = alert.querySelector('.alert-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => alert.remove());
    }
    setTimeout(() => {
      alert.style.transition = 'opacity 0.5s ease';
      alert.style.opacity = '0';
      setTimeout(() => alert.remove(), 500);
    }, 8000);
  });

  // ==========================================================================
  // Drag and Drop File Upload
  // ==========================================================================
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const preview = document.getElementById('file-preview');
  const fileNameDisplay = document.getElementById('file-name');
  const fileSizeDisplay = document.getElementById('file-size');
  const submitBtn = document.getElementById('submit-upload-btn');

  if (dropzone && fileInput) {
    ['dragenter', 'dragover'].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
      }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
      }, false);
    });

    dropzone.addEventListener('drop', (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files.length) {
        fileInput.files = files;
        handleFileSelect(files[0]);
      }
    });

    fileInput.addEventListener('change', () => {
      if (fileInput.files.length) {
        handleFileSelect(fileInput.files[0]);
      }
    });

    function handleFileSelect(file) {
      if (!file.name.toLowerCase().endsWith('.csv')) {
        alert('Please select a valid CSV (.csv) file.');
        fileInput.value = '';
        if (preview) preview.style.display = 'none';
        if (submitBtn) submitBtn.disabled = true;
        return;
      }

      if (preview && fileNameDisplay && fileSizeDisplay) {
        fileNameDisplay.textContent = file.name;
        fileSizeDisplay.textContent = formatBytes(file.size);
        preview.style.display = 'flex';
      }
      if (submitBtn) {
        submitBtn.disabled = false;
      }
    }
  }

  // ==========================================================================
  // Copy to Clipboard
  // ==========================================================================
  const copyBtns = document.querySelectorAll('.btn-copy');
  copyBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-target');
      const targetElem = document.getElementById(targetId);
      if (targetElem) {
        const textToCopy = targetElem.innerText || targetElem.textContent;
        navigator.clipboard.writeText(textToCopy).then(() => {
          const originalText = btn.innerHTML;
          btn.innerHTML = '<svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M12.736 3.97a.733.733 0 0 1 1.047 0c.286.289.29.756.01 1.05L7.88 12.01a.733.733 0 0 1-1.065.02L3.217 8.384a.757.757 0 0 1 0-1.06.733.733 0 0 1 1.047 0l3.052 3.093 5.4-6.425a.247.247 0 0 1 .02-.022Z"/></svg> Copied!';
          setTimeout(() => {
            btn.innerHTML = originalText;
          }, 2000);
        });
      }
    });
  });

  // ==========================================================================
  // Table Live Search / Filter
  // ==========================================================================
  const searchInput = document.getElementById('table-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const query = e.target.value.toLowerCase().trim();
      const rows = document.querySelectorAll('.searchable-table tbody tr');
      rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(query) ? '' : 'none';
      });
    });
  }

  // ==========================================================================
  // Tab Switcher for JSON Viewer
  // ==========================================================================
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const tabTarget = btn.getAttribute('data-tab');
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.style.display = 'none');

      btn.classList.add('active');
      const activePane = document.getElementById(tabTarget);
      if (activePane) activePane.style.display = 'block';
    });
  });

  // Helper function: byte format
  function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  }
});
