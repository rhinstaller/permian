function expand_nextSibling(elem) {
    siblingStyle = elem.nextSibling.style;
    if (siblingStyle.maxHeight != 'none') {
        // Set maxHeight explicitly to none overriding the max-height for this
        // specific element.
        siblingStyle.maxHeight = 'none';
        siblingStyle.overflowX = 'auto';
        elem.innerText = '▲'
    }
    else {
        // Remove the maxHeight override.
        siblingStyle.removeProperty('max-height');
        siblingStyle.removeProperty('overflow-x');
        elem.innerText = '▼'
    }
}
