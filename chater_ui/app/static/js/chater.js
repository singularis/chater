document.addEventListener('DOMContentLoaded', function () {
    // Select all buttons
    const buttons = document.querySelectorAll('.btn');

    // Add click effect to all buttons
    buttons.forEach(button => {
        button.addEventListener('mousedown', function () {
            this.classList.add('clicked');
            setTimeout(() => {
                this.classList.remove('clicked');
            }, 200); // 200 milliseconds
        });
    });

    // Handle textarea input and submission
    const textarea = document.getElementById('question');
    textarea.addEventListener('keydown', function (e) {
        // Submit the form when Enter is pressed without Shift
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            document.querySelector('.btn[type="submit"]').click();
        }
    });

    // Auto-resize textarea based on content
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';

    textarea.addEventListener('input', function () {
        if (this.scrollHeight > this.clientHeight) {
            this.style.height = 'auto';
            this.style.height = this.scrollHeight + 'px';
        }
    });

    // Initialize collapsible blocks
    manageCollapsibleBlocks();

    // Observe changes to the container to manage collapsible blocks dynamically
    const observer = new MutationObserver(manageCollapsibleBlocks);
    const target = document.querySelector('.container');
    const config = { childList: true, subtree: true };

    observer.observe(target, config);

    // Manage the toggle switch
    const toggleSwitch = document.getElementById('toggle-switch');

    // Fetch the current switch state from local storage on page load
    const savedSwitchState = localStorage.getItem('toggleSwitchState');
    if (savedSwitchState) {
        toggleSwitch.checked = (savedSwitchState === 'on');
    }

    // Fetch the current switch state from the server on page load
    fetch('get-switch-state')
        .then(response => response.json())
        .then(data => {
            // Set the switch state based on server response if not found in local storage
            if (!savedSwitchState) {
                toggleSwitch.checked = (data.state === 'on');
            }
        })
        .catch(error => console.error('Error fetching switch state:', error));

    // Event listener to handle switch state changes
    toggleSwitch.addEventListener('change', function () {
        const switchState = this.checked ? 'on' : 'off';
        // Save the new switch state to local storage
        localStorage.setItem('toggleSwitchState', switchState);

        // Send the new switch state to the server
        fetch('toggle-switch', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ state: switchState })
        })
            .then(response => response.json())
            .then(data => {
                console.log('Switch state updated:', data);
            })
            .catch(error => {
                console.error('Error updating switch state:', error);
            });
    });

    // Manage the dev mode switch
    const devModeSwitch = document.getElementById('dev-mode-switch');

    // Fetch from local storage
    const savedDevModeState = localStorage.getItem('devModeSwitchState');
    if (savedDevModeState) {
        devModeSwitch.checked = (savedDevModeState === 'on');
    }

    // Fetch from server
    fetch('get-dev-mode-state')
        .then(response => response.json())
        .then(data => {
            if (!savedDevModeState) {
                devModeSwitch.checked = (data.dev_mode === 'on');
            }
        })
        .catch(error => console.error('Error fetching dev mode state:', error));

    // Event listener
    devModeSwitch.addEventListener('change', function () {
        const switchState = this.checked ? 'on' : 'off';
        localStorage.setItem('devModeSwitchState', switchState);

        fetch('toggle-dev-mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: switchState })
        })
            .then(response => response.json())
            .then(data => {
                console.log('Dev mode updated:', data);
            })
            .catch(error => {
                console.error('Error updating dev mode:', error);
            });
    });
});

// Function to manage collapsible blocks
function manageCollapsibleBlocks() {
    const headers = document.querySelectorAll('.collapsible-header');
    const contents = document.querySelectorAll('.collapsible-content');

    // Add event listeners to collapsible headers
    headers.forEach(header => {
        header.removeEventListener('click', toggleHandler);
        header.addEventListener('click', toggleHandler);
    });

    // Initialize first collapsible content as open, others as closed
    contents.forEach((content, index) => {
        if (index === 0) {
            content.style.display = "block";
            content.style.maxHeight = content.scrollHeight + "px";
        } else {
            content.style.display = "none";
            content.style.maxHeight = "0px";
        }
    });
}

// Function to handle toggling of collapsible content
function toggleHandler() {
    const content = this.nextElementSibling;
    const allContents = document.querySelectorAll('.collapsible-content');

    // Close other collapsible contents
    allContents.forEach(otherContent => {
        if (otherContent !== content) {
            otherContent.style.maxHeight = "0px";
            setTimeout(() => {
                otherContent.style.display = "none";
            }, 300);
        }
    });

    // Toggle current collapsible content
    if (content.style.maxHeight === "0px" || content.style.display === "none") {
        content.style.display = "block";
        content.style.maxHeight = content.scrollHeight + "px";
    } else {
        content.style.maxHeight = "0px";
        setTimeout(() => {
            content.style.display = "none";
        }, 300);
    }
}
