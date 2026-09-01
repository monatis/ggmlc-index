function openLinkInNewTab(link) {
  window.open(link, '_blank');
}

function redirectToIndex() {
  window.location.href = "../index.html";
}

function copyInstallCmd() {
  const cmdElem = document.getElementById('pip-install-cmd');
  if (!cmdElem) return;
  const cmdText = cmdElem.innerText;
  navigator.clipboard.writeText(cmdText).then(() => {
    const copyText = document.getElementById('copy-text');
    if (copyText) {
      const originalText = copyText.innerText;
      copyText.innerText = "Copied!";
      setTimeout(() => {
        copyText.innerText = originalText;
      }, 2000);
    }
  }).catch(err => {
    console.error('Failed to copy: ', err);
  });
}

function getRepoInfo() {
  let owner = (typeof window.current_repo_owner !== 'undefined' && window.current_repo_owner) ? window.current_repo_owner : '';
  let repo = (typeof window.current_repo_name !== 'undefined' && window.current_repo_name) ? window.current_repo_name : '';

  if (!owner || owner.startsWith('_')) {
    owner = document.body ? document.body.getAttribute('data-owner') : '';
  }
  if (!repo || repo.startsWith('_')) {
    repo = document.body ? document.body.getAttribute('data-repo') : '';
  }

  // Fallback: extract from homepage button
  if (!owner || !repo || owner.startsWith('_') || repo.startsWith('_')) {
    const btn = document.getElementById('repoHomepage');
    if (btn && btn.getAttribute('onclick')) {
      const match = btn.getAttribute('onclick').match(/github\.com\/([^\/]+)\/([^\/'"]+)/);
      if (match) {
        owner = match[1];
        repo = match[2];
      }
    }
  }

  return {
    owner: (owner && !owner.startsWith('_')) ? owner : 'monatis',
    repo: (repo && !repo.startsWith('_')) ? repo : 'ggmlc'
  };
}

function selectVersion(tag, updateHash = true) {
  // Update version selector highlight
  const allVersionItems = document.querySelectorAll('.version-item');
  allVersionItems.forEach(item => item.classList.remove('selected'));
  
  const selectedItem = document.getElementById('ver-' + tag);
  if (selectedItem) {
    selectedItem.classList.add('selected');
  }

  // Toggle file lists
  const allFileSections = document.querySelectorAll('.files-version-section');
  allFileSections.forEach(sec => sec.style.display = 'none');

  const selectedFileSec = document.getElementById('files-' + tag);
  if (selectedFileSec) {
    selectedFileSec.style.display = 'block';
  }

  if (updateHash) {
    history.replaceState(null, null, '#' + tag);
  }

  loadReadme(tag);
}

function loadReadme(tag) {
  const container = document.getElementById('markdown-container');
  if (!container) return;

  container.innerHTML = '<div class="loading-readme">Loading documentation for ' + tag + '...</div>';

  const { owner, repo } = getRepoInfo();

  const candidateUrls = [
    `https://raw.githubusercontent.com/${owner}/${repo}/${tag}/README.md`,
    `https://raw.githubusercontent.com/${owner}/${repo}/main/README.md`,
    `https://raw.githubusercontent.com/${owner}/${repo}/master/README.md`
  ];

  function tryFetch(index) {
    if (index >= candidateUrls.length) {
      container.innerHTML = '<p class="text-muted">No README documentation found for this release.</p>';
      return;
    }
    fetch(candidateUrls[index])
      .then(response => {
        if (!response.ok) {
          throw new Error('Not found');
        }
        return response.text();
      })
      .then(markdown => {
        container.innerHTML = marked.parse(markdown);
      })
      .catch(() => {
        tryFetch(index + 1);
      });
  }

  tryFetch(0);
}

document.addEventListener('DOMContentLoaded', () => {
  let activeTag = '';
  if (window.location.hash) {
    activeTag = window.location.hash.replace('#', '');
  }
  if (!activeTag || !document.getElementById('ver-' + activeTag)) {
    const latestTagElem = document.getElementById('latest-tag');
    if (latestTagElem && latestTagElem.textContent.trim()) {
      activeTag = latestTagElem.textContent.trim();
    } else {
      const firstVerItem = document.querySelector('.version-item');
      if (firstVerItem) {
        activeTag = firstVerItem.id.replace('ver-', '');
      }
    }
  }

  if (activeTag) {
    selectVersion(activeTag, false);
  }
});
