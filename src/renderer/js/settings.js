document.addEventListener('DOMContentLoaded', () => {
    const themeButtons = document.querySelectorAll('.theme-button');

    themeButtons.forEach(button => {
        button.addEventListener('click', (event) => {
            const target = event.target.closest('.theme-button');
            if (!target) return;

            const theme = target.getAttribute('data-theme');
            if (!theme) return;

            // Update active state
            themeButtons.forEach(btn => btn.classList.remove('active'));
            target.classList.add('active');

            // Apply theme
            document.body.className = `theme-${theme}`;
            localStorage.setItem('sentinel-theme', theme);
        });
    });

    // Initialize theme
    const savedTheme = localStorage.getItem('sentinel-theme') || 'cyberpunk';
    document.body.className = `theme-${savedTheme}`;
    themeButtons.forEach(button => {
        if (button.getAttribute('data-theme') === savedTheme) {
            button.classList.add('active');
        } else {
            button.classList.remove('active');
        }
    });
});