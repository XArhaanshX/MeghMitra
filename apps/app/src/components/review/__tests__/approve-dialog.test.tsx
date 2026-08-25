import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type * as ReviewApi from '@/api/review';
import { approveRule } from '@/api/review';

import { ApproveDialog } from '../approve-dialog';

vi.mock('@/api/review', async importOriginal => {
  const actual = await importOriginal<typeof ReviewApi>();
  return { ...actual, approveRule: vi.fn() };
});

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const mockedApproveRule = vi.mocked(approveRule);

describe('ApproveDialog', () => {
  it('disables the trigger when no valid citation exists', () => {
    renderWithClient(<ApproveDialog ruleId="rule-1" disabled />);
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
  });

  it('blocks submission until a reviewer name is entered', async () => {
    const user = userEvent.setup();
    renderWithClient(<ApproveDialog ruleId="rule-1" />);

    await user.click(screen.getByRole('button', { name: 'Approve' }));
    await user.click(screen.getByRole('button', { name: 'Confirm approval' }));

    expect(mockedApproveRule).not.toHaveBeenCalled();
  });

  it('submits the reviewer name to POST /rules/{id}/approve', async () => {
    mockedApproveRule.mockResolvedValueOnce({
      id: 'rule-1',
      document_id: null,
      fields: {
        state: 'Haryana',
        district: 'Sirsa',
        block: null,
        farming_situation: null,
        crop: null,
        soil: null,
        crop_stage: null,
        condition: 'Dry spell after sowing',
        condition_code: null,
        action: null,
        variety: null,
        seed_rate: null,
        actor: null,
      },
      citation: { document: 'doc.pdf', page: 9, source_text: null, bounding_region: null },
      confidence: 0.9,
      extractor_version: '1.0.0',
      extracted_at: '2020-07-15T00:00:00Z',
      review_status: 'approved',
      reviewed_by: 'Priya',
      reviewed_at: '2020-07-16T00:00:00Z',
      notes: [],
    });

    const user = userEvent.setup();
    renderWithClient(<ApproveDialog ruleId="rule-1" />);

    await user.click(screen.getByRole('button', { name: 'Approve' }));
    await user.type(screen.getByLabelText('Your name'), 'Priya');
    await user.click(screen.getByRole('button', { name: 'Confirm approval' }));

    await waitFor(() =>
      expect(mockedApproveRule).toHaveBeenCalledWith('rule-1', { reviewed_by: 'Priya' })
    );
  });
});
