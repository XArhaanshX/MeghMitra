import { AxiosError } from 'axios';
import { describe, expect, it } from 'vitest';
import * as z from 'zod';

import { ApiError, isApiError, toApiError } from '../errors';

describe('ApiError', () => {
  it('is an instance of Error', () => {
    const e = new ApiError({ message: 'fail', status: 400 });
    expect(e).toBeInstanceOf(Error);
    expect(e).toBeInstanceOf(ApiError);
  });

  it('exposes status, code, and details', () => {
    const e = new ApiError({ message: 'oops', status: 422, code: 'INVALID', details: { x: 1 } });
    expect(e.message).toBe('oops');
    expect(e.status).toBe(422);
    expect(e.code).toBe('INVALID');
    expect(e.details).toEqual({ x: 1 });
  });
});

describe('isApiError', () => {
  it('returns true for ApiError', () => {
    expect(isApiError(new ApiError({ message: 'x' }))).toBe(true);
  });

  it('returns false for a plain Error', () => {
    expect(isApiError(new Error('x'))).toBe(false);
  });

  it('returns false for non-errors', () => {
    expect(isApiError('string')).toBe(false);
    expect(isApiError(null)).toBe(false);
  });
});

describe('toApiError', () => {
  it('passes ApiError through unchanged', () => {
    const e = new ApiError({ message: 'x' });
    expect(toApiError(e)).toBe(e);
  });

  it('converts a 404 HTTPException string detail', () => {
    const axiosErr = new AxiosError('Request failed', 'ERR_BAD_RESPONSE');
    Object.defineProperty(axiosErr, 'response', {
      value: { status: 404, data: { detail: 'rule not found' } },
    });
    const result = toApiError(axiosErr);
    expect(result).toBeInstanceOf(ApiError);
    expect(result.status).toBe(404);
    expect(result.message).toBe('rule not found');
  });

  it('converts a 422 domain-error string detail', () => {
    const axiosErr = new AxiosError('Request failed', 'ERR_BAD_RESPONSE');
    Object.defineProperty(axiosErr, 'response', {
      value: { status: 422, data: { detail: 'cannot approve a rule without a valid citation' } },
    });
    const result = toApiError(axiosErr);
    expect(result.status).toBe(422);
    expect(result.message).toBe('cannot approve a rule without a valid citation');
  });

  it('joins a 422 request-validation array detail into one message', () => {
    const axiosErr = new AxiosError('Request failed', 'ERR_BAD_RESPONSE');
    Object.defineProperty(axiosErr, 'response', {
      value: {
        status: 422,
        data: {
          detail: [
            { loc: ['body', 'reviewed_by'], msg: 'Field required', type: 'missing' },
            { loc: ['body', 'reason'], msg: 'Input should be a valid string', type: 'string_type' },
          ],
        },
      },
    });
    const result = toApiError(axiosErr);
    expect(result.message).toBe('Field required; Input should be a valid string');
  });

  it('reports a fixed message for 503 regardless of body', () => {
    const axiosErr = new AxiosError('Request failed', 'ERR_BAD_RESPONSE');
    Object.defineProperty(axiosErr, 'response', {
      value: { status: 503, data: {} },
    });
    const result = toApiError(axiosErr);
    expect(result.status).toBe(503);
    expect(result.message).toBe('Database unavailable');
  });

  it('converts AxiosError without response', () => {
    const axiosErr = new AxiosError('Network Error');
    const result = toApiError(axiosErr);
    expect(result).toBeInstanceOf(ApiError);
    expect(result.message).toBe('Network Error');
  });

  it('converts a ZodError produced by schema parsing', () => {
    const parsed = z.string().min(10).safeParse('x');
    if (parsed.success) throw new Error('expected parse failure');
    const result = toApiError(parsed.error);
    expect(result).toBeInstanceOf(ApiError);
    expect(result.code).toBe('VALIDATION_ERROR');
  });

  it('converts a plain Error', () => {
    const result = toApiError(new Error('boom'));
    expect(result).toBeInstanceOf(ApiError);
    expect(result.message).toBe('boom');
  });

  it('converts unknown values', () => {
    const result = toApiError('something weird');
    expect(result).toBeInstanceOf(ApiError);
    expect(result.message).toBe('An unexpected error occurred');
  });
});
