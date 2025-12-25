"""
CSS styles for FinMycelium web interface.
"""

# Base styling
BASE_STYLES = """
<style>
/* Base styling */
.reconstruction-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 1.5rem;
    border-radius: 10px;
    color: white;
    margin-bottom: 2rem;
}
.section-card {
    background: white;
    padding: 1.5rem;
    border-radius: 10px;
    border-left: 4px solid #667eea;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    margin-bottom: 1rem;
}
.subsection-card {
    background: #f8f9fa;
    padding: 1rem;
    border-radius: 8px;
    border-left: 3px solid #764ba2;
    margin-bottom: 0.5rem;
}
.metric-badge {
    display: inline-block;
    background: #e3f2fd;
    color: #1976d2;
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    font-size: 0.875rem;
    margin: 0.25rem;
}
.confidence-badge {
    display: inline-block;
    background: #e8f5e9;
    color: #2e7d32;
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    font-size: 0.875rem;
    margin: 0.25rem;
}

/* Timeline styling */
.timeline-container {
    position: relative;
    margin-left: 3.5rem;
    padding-bottom: 2rem;
}
.timeline-line {
    position: absolute;
    left: -1.75rem;
    top: 0;
    bottom: 0;
    width: 4px;
    background: linear-gradient(to bottom, #667eea, #764ba2);
    border-radius: 2px;
}
.timeline-item {
    position: relative;
    margin-bottom: 2rem;
    padding-left: 0.5rem;
}
.timeline-dot {
    position: absolute;
    left: -2rem;
    top: 0.5rem;
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 50%;
    background: white;
    border: 4px solid #667eea;
    z-index: 1;
}
.timeline-dot-stage {
    border-color: #667eea;
    background: #667eea;
}
.timeline-dot-episode {
    border-color: #764ba2;
    background: #764ba2;
}
.timeline-content {
    background: white;
    padding: 1.5rem;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    border: 1px solid #e2e8f0;
    margin-bottom: 1.5rem;
}

/* Timeline headers */
.timeline-stage-header {
    color: #667eea;
    font-weight: bold;
    margin-bottom: 1rem;
    font-size: 1.2rem;
    margin-top: 0;
    padding-top: 0;
    border-bottom: 2px solid #667eea;
    padding-bottom: 0.5rem;
}
.timeline-episode-header {
    color: #764ba2;
    font-weight: bold;
    margin-bottom: 1rem;
    font-size: 1.1rem;
    margin-top: 0;
    padding-top: 0;
    border-bottom: 2px solid #764ba2;
    padding-bottom: 0.5rem;
}

/* Time labels positioning */
.timeline-time-label {
    position: absolute;
    left: -5rem;
    top: 0.75rem;
    font-size: 0.8rem;
    color: #666;
    white-space: nowrap;
    width: 4.5rem;
    text-align: right;
    font-weight: 600;
}

/* Evidence styling */
.evidence-card {
    background: #f5fafe;
    padding: 1rem;
    border-radius: 6px;
    margin: 0.75rem 0;
    font-size: 0.9rem;
}
.reasons-list {
    margin-left: 1rem;
    margin-top: 0.5rem;
    font-size: 0.9rem;
    color: #444;
}

/* Expander styling */
div[data-testid="stExpander"] > div:first-child {
    background-color: #f8f9fa;
    padding: 0.5rem 1rem;
    border-radius: 8px 8px 0 0;
    border-left: 3px solid #667eea;
}

/* Field key styling */
.field-key {
    font-weight: 700 !important;
    color: #2d3748 !important;
}
.timeline-content p strong,
.subsection-card p strong,
.evidence-card strong {
    font-weight: 700 !important;
    color: #2c5282 !important;
    background-color: #f7fafc;
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
}
.field-label {
    font-weight: 700;
    color: #2c5282;
    background-color: #f7fafc;
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
    margin-right: 0.5rem;
    display: inline-block;
}

/* Data fields */
.data-field {
    margin-bottom: 0.75rem;
}

/* Responsive adjustments */
@media (max-width: 768px) {
    .timeline-container {
        margin-left: 3rem;
    }
    .timeline-time-label {
        left: -4.5rem;
        font-size: 0.75rem;
        width: 4rem;
    }
}

/* Typography */
h1 {
    font-size: 1.8rem;
    color: #2d3748;
}
h2 {
    font-size: 1.5rem;
    color: #2d3748;
}
h3 {
    font-size: 1.3rem;
    color: #2d3748;
}
h4 {
    font-size: 1.1rem;
    color: #2d3748;
    margin-top: 0;
    margin-bottom: 1rem;
}
h5 {
    font-size: 1rem;
    color: #2d3748;
    margin-top: 0;
    margin-bottom: 1rem;
}
h6 {
    font-size: 0.9rem;
    color: #2d3748;
}
p, li, span {
    font-size: 0.9rem;
    line-height: 1.6;
}
</style>
"""

# Simplified styles for class build results
CLASS_BUILD_STYLES = """
<style>
.reconstruction-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 1.5rem;
    border-radius: 10px;
    color: white;
    margin-bottom: 1rem;
}
.section-card {
    background: white;
    padding: 1.5rem;
    border-radius: 10px;
    border-left: 4px solid #667eea;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    margin-bottom: 1rem;
}
.subsection-card {
    background: #f8f9fa;
    padding: 1rem;
    border-radius: 8px;
    border-left: 3px solid #764ba2;
    margin-bottom: 0.5rem;
}
.metric-badge {
    display: inline-block;
    background: #e3f2fd;
    color: #1976d2;
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    font-size: 0.875rem;
    margin: 0.25rem;
}
.timeline-item {
    border-left: 2px solid #667eea;
    padding-left: 1rem;
    margin-left: 0.5rem;
    margin-bottom: 1rem;
}
</style>
"""

