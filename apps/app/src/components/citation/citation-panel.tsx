import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { Citation } from '@/schemas';

interface CitationPanelProps {
  citation: Citation | null | undefined;
  isLoading?: boolean;
  heading?: string;
}

// The brand moment: proof that a recommendation traces back to an exact
// page of a real DACP document. Reused on the rule detail page and the
// evaluate result panel -- keep both call sites visually identical.
export function CitationPanel({
  citation,
  isLoading = false,
  heading = 'Why Ankur said this',
}: CitationPanelProps) {
  return (
    <Card className="border-primary/30 bg-primary/5">
      <CardHeader>
        <CardTitle className="text-lg">{heading}</CardTitle>
        <p className="text-sm text-muted-foreground">
          Traceable to the exact page of the source DACP document.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <p className="text-sm text-muted-foreground">Loading citation…</p>}
        {!isLoading && !citation && (
          <p className="text-sm text-muted-foreground">No citation available.</p>
        )}
        {citation && (
          <>
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="font-medium">{citation.document}</span>
              <span className="text-3xl font-semibold tracking-tight text-primary">
                p.{citation.page}
              </span>
            </div>
            <blockquote className="border-l-2 border-primary/40 pl-3 text-sm text-muted-foreground italic">
              {citation.source_text ? `"${citation.source_text}"` : 'No source snippet captured.'}
            </blockquote>
            {citation.bounding_region && (
              <p className="text-xs text-muted-foreground">Region: {citation.bounding_region}</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
