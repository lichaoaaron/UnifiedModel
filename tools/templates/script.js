// MModel HTML文档生成器JavaScript文件

// 树状目录折叠/展开
function toggleTocItem(element) {
    const children = element.parentElement.nextElementSibling;
    if (children && children.classList.contains('toc-children')) {
        children.classList.toggle('collapsed');
        element.textContent = children.classList.contains('collapsed') ? '▶' : '▼';
    }
}

// 展开所有目录项
function expandAll() {
    const allChildren = document.querySelectorAll('.toc-children');
    const allToggles = document.querySelectorAll('.toc-toggle');
    
    allChildren.forEach(child => {
        child.classList.remove('collapsed');
    });
    
    allToggles.forEach(toggle => {
        toggle.textContent = '▼';
    });
}

// 折叠所有目录项
function collapseAll() {
    const allChildren = document.querySelectorAll('.toc-children');
    const allToggles = document.querySelectorAll('.toc-toggle');
    
    allChildren.forEach(child => {
        child.classList.add('collapsed');
    });
    
    allToggles.forEach(toggle => {
        toggle.textContent = '▶';
    });
}

// 只展开到指定层级
function expandToLevel(maxLevel) {
    const allLinks = document.querySelectorAll('.toc-link');
    
    allLinks.forEach(link => {
        // 从类名中提取层级
        const levelMatch = link.className.match(/level-(\d+)/);
        if (levelMatch) {
            const level = parseInt(levelMatch[1]);
            const tocItem = link.parentElement;
            const children = tocItem.nextElementSibling;
            const toggle = tocItem.querySelector('.toc-toggle');
            
            if (children && children.classList.contains('toc-children')) {
                if (level < maxLevel) {
                    children.classList.remove('collapsed');
                    if (toggle) toggle.textContent = '▼';
                } else {
                    children.classList.add('collapsed');
                    if (toggle) toggle.textContent = '▶';
                }
            }
        }
    });
}

// 平滑滚动到锚点
document.addEventListener('DOMContentLoaded', function() {
    // 在侧边栏顶部添加展开/折叠按钮
    const sidebar = document.querySelector('.sidebar');
    const tocTitle = sidebar.querySelector('h3');
    
    const controlsDiv = document.createElement('div');
    controlsDiv.style.cssText = 'margin-bottom: 10px; display: flex; gap: 5px;';
    controlsDiv.innerHTML = `
        <button onclick="expandAll()" style="padding: 4px 8px; font-size: 12px; cursor: pointer; border: 1px solid #ddd; border-radius: 3px; background: white;">Expand All</button>
        <button onclick="collapseAll()" style="padding: 4px 8px; font-size: 12px; cursor: pointer; border: 1px solid #ddd; border-radius: 3px; background: white;">Collapse All</button>
        <button onclick="expandToLevel(3)" style="padding: 4px 8px; font-size: 12px; cursor: pointer; border: 1px solid #ddd; border-radius: 3px; background: white;">Expand 3 Levels</button>
    `;
    
    tocTitle.insertAdjacentElement('afterend', controlsDiv);
    
    // 点击目录链接时平滑滚动
    const tocLinks = document.querySelectorAll('.toc-link');
    tocLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href').substring(1);
            const targetElement = document.getElementById(targetId);
            if (targetElement) {
                targetElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
                // 高亮目标元素
                targetElement.classList.add('highlight');
                setTimeout(() => {
                    targetElement.classList.remove('highlight');
                }, 2000);
            }
        });
    });
    
    // 自动展开包含当前锚点的目录项
    const hash = window.location.hash;
    if (hash) {
        const targetLink = document.querySelector(`.toc-link[href="${hash}"]`);
        if (targetLink) {
            let parent = targetLink.parentElement;
            while (parent) {
                if (parent.classList.contains('toc-children')) {
                    parent.classList.remove('collapsed');
                    const toggle = parent.previousElementSibling?.querySelector('.toc-toggle');
                    if (toggle) {
                        toggle.textContent = '▼';
                    }
                }
                parent = parent.parentElement;
            }
            
            // 滚动到目标元素
            setTimeout(() => {
                const targetElement = document.querySelector(hash);
                if (targetElement) {
                    targetElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }, 100);
        }
    }
});

// 添加高亮动画样式
const style = document.createElement('style');
style.textContent = `
    .highlight {
        animation: highlight 2s ease-out;
    }
    @keyframes highlight {
        0% { background-color: #fffbdd; }
        100% { background-color: transparent; }
    }
    
    /* 按钮悬停效果 */
    button:hover {
        background-color: #f8f9fa !important;
        border-color: #0366d6 !important;
        color: #0366d6;
    }
`;
document.head.appendChild(style);

// 高亮当前章节
window.addEventListener('scroll', function() {
    const sections = document.querySelectorAll('[id]');
    const navLinks = document.querySelectorAll('.toc-link');
    
    let current = '';
    sections.forEach(section => {
        const sectionTop = section.offsetTop;
        if (pageYOffset >= sectionTop - 200) {
            current = section.getAttribute('id');
        }
    });
    
    navLinks.forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === '#' + current) {
            link.classList.add('active');
            link.style.backgroundColor = '#f1f8ff';
            link.style.color = '#0366d6';
        } else {
            link.style.backgroundColor = '';
            link.style.color = '';
        }
    });
});

// 初始化：默认展开第一级
document.addEventListener('DOMContentLoaded', function() {
    const firstLevelToggles = document.querySelectorAll('.toc-tree > li > .toc-item > .toc-toggle');
    firstLevelToggles.forEach(toggle => {
        // 默认展开第一级
    });
}); 