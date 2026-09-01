function openLinkInNewTab(link) {
  window.open(link, '_blank');
}

function redirectToIndex() {
  window.location.href = "../index.html";
}

function copyInstallCmd() {
  const cmdText = document.getElementById('pip-install-cmd').innerText;
  navigator.clipboard.writeText(cmdText).then(() => {
    const copyText = document.getElementById('copy-text');
    const originalText = copyText.innerText;
    copyText.innerText = "Copied!";
    setTimeout(() => {
      copyText.innerText = originalText;
    }, 2000);
  }).catch(err => {
    console.error('Failed to copy: ', err);
  });
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
  container.innerHTML = '<div class="loading-readme">Loading documentation for ' + tag + '...</div>';

  const candidateUrls = [
    `https://raw.githubusercontent.com/${current_repo_owner}/${current_repo_name}/${tag}/README.md`,
    `https://raw.githubusercontent.com/${current_repo_owner}/${current_repo_name}/main/README.md`,
    `https://raw.githubusercontent.com/${current_repo_owner}/${current_repo_name}/master/README.md`
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
