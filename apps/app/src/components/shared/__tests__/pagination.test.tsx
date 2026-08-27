import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Pagination } from '../pagination';

// The offset arithmetic here decides which slice of an India-wide corpus a
// reviewer is looking at, so the boundaries are worth pinning: an off-by-one
// silently skips or repeats a page of government rules.
describe('Pagination', () => {
  it('states the count and renders no controls when everything fits on one page', () => {
    render(<Pagination total={9} limit={25} offset={0} onOffsetChange={vi.fn()} unit="rules" />);

    expect(screen.getByText(/9 rules, all shown/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument();
  });

  it('reports the current range and page position', () => {
    render(<Pagination total={9389} limit={25} offset={50} onOffsetChange={vi.fn()} unit="rules" />);

    expect(screen.getByText(/51 to 75/)).toBeInTheDocument();
    expect(screen.getByText(/of 9,389 rules/)).toBeInTheDocument();
    expect(screen.getByText('Page 3 of 376')).toBeInTheDocument();
  });

  it('disables Previous on the first page and Next on the last', () => {
    const { rerender } = render(
      <Pagination total={60} limit={25} offset={0} onOffsetChange={vi.fn()} />
    );
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled();

    // Final page holds the remainder (10 of 60), not a full 25.
    rerender(<Pagination total={60} limit={25} offset={50} onOffsetChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Previous' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    expect(screen.getByText(/51 to 60/)).toBeInTheDocument();
  });

  it('steps the offset by exactly one page in each direction', async () => {
    const onOffsetChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Pagination total={200} limit={25} offset={75} onOffsetChange={onOffsetChange} />
    );

    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(onOffsetChange).toHaveBeenLastCalledWith(100);

    await user.click(screen.getByRole('button', { name: 'Previous' }));
    expect(onOffsetChange).toHaveBeenLastCalledWith(50);
  });

  it('never proposes a negative offset', async () => {
    const onOffsetChange = vi.fn();
    const user = userEvent.setup();
    // An offset that is not a clean multiple of the limit, as a hand-edited
    // URL can produce.
    render(<Pagination total={200} limit={25} offset={10} onOffsetChange={onOffsetChange} />);

    await user.click(screen.getByRole('button', { name: 'Previous' }));
    expect(onOffsetChange).toHaveBeenLastCalledWith(0);
  });

  it('announces the range politely so paging is not silent', () => {
    render(<Pagination total={200} limit={25} offset={0} onOffsetChange={vi.fn()} unit="rules" />);

    expect(screen.getByRole('navigation', { name: 'rules pagination' })).toBeInTheDocument();
    expect(screen.getByText(/of 200 rules/).closest('p')).toHaveAttribute('aria-live', 'polite');
  });
});
