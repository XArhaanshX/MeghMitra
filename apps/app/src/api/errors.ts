import { isAxiosError } from 'axios';
import { ZodError } from 'zod';

import type { ApiErrorData } from '@/types';

export class ApiError extends Error {
  readonly status?: number;
  readonly code?: string;
  readonly details?: unknown;

  constructor({ message, status, code, details }: ApiErrorData) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

interface FastApiValidationIssue {
  loc: Array<string | number>;
  msg: string;
  type: string;
}

interface FastApiErrorBody {
  detail?: string | FastApiValidationIssue[];
}

// FastAPI sends `{ detail: "..." }` for HTTPException (404, 422 domain
// errors) and `{ detail: [{ loc, msg, type }] }` for request-validation
// failures -- never `.message`. This is the only place that shape is unpacked.
function messageFromResponse(
  data: FastApiErrorBody | undefined,
  status: number | undefined
): string {
  if (status === 503) return 'Database unavailable';
  const detail = data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(issue => issue.msg).join('; ');
  return '';
}

export function toApiError(error: unknown): ApiError {
  if (isApiError(error)) return error;

  if (isAxiosError(error)) {
    const status = error.response?.status;
    const data = error.response?.data as FastApiErrorBody | undefined;
    return new ApiError({
      message: messageFromResponse(data, status) || error.message,
      status,
      details: data,
    });
  }

  if (error instanceof ZodError) {
    return new ApiError({
      message: 'Validation error',
      code: 'VALIDATION_ERROR',
      details: error.issues,
    });
  }

  if (error instanceof Error) {
    return new ApiError({ message: error.message });
  }

  return new ApiError({ message: 'An unexpected error occurred' });
}
