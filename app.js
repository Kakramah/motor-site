document.addEventListener('DOMContentLoaded', () => {
    // Scroll Parallax for Hero Image
    const heroImg = document.querySelector('.hero-img');
    const heroContent = document.querySelector('.hero-content');
    
    window.addEventListener('scroll', () => {
        const scrolled = window.scrollY;
        if (heroImg) {
            // Scale up the image as you scroll down
            const scale = 1 + (scrolled * 0.0005);
            heroImg.style.transform = `scale(${scale})`;
            
            // Fade out the content
            if(heroContent) {
                heroContent.style.opacity = 1 - (scrolled * 0.002);
                heroContent.style.transform = `translateY(${scrolled * 0.3}px)`;
            }
        }
    });

    // Intersection Observer for scroll reveal animations
    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.15
    };

    const observer = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    const revealElements = document.querySelectorAll('.scroll-reveal');
    revealElements.forEach(el => observer.observe(el));
});
